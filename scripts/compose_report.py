#!/usr/bin/env python3
"""Compose a recruitment big-data report by orchestrating the recruitment MCP.

Calls the upstream recruitment-mcp-server tools and assembles a structured JSON
payload rendered into a professional HTML / Markdown report. Supports
``--dry-run`` which returns a well-formed skeleton from the bundled sample data
WITHOUT contacting the MCP.

Workflow:
  1. Require a confirmed enterprise name or an explicit enterprise identifier.
  2. Route the user's question to the requested MCP tools and report sections.
  3. Apply city/job filters to the collected pages, with clear sample scope.
  4. Render JSON and optionally HTML + Markdown. Default to a dry-run sample;
     real and potentially chargeable calls require the explicit ``--live`` flag.

This file never prints secrets; MCP credentials live in the server's own .env.
"""
from __future__ import annotations

import argparse
import calendar
import datetime as dt
import json
import pathlib
import re
from typing import Any, Dict, List, Mapping, Optional, Sequence

from common import REPORT_BANNER, REPORT_TYPE, call_tool_once, collect_detail_pages, json_dumps, load_json_file, paid_call_scope, print_json
import mcp_client
from render_report import render_html, render_markdown, html_to_pdf
from benefits import benefit_sections, organize_benefits

SAMPLE_PATH = pathlib.Path(__file__).resolve().parent.parent / "assets" / "report.example.json"

# Only the report's recruitment-data tools are orchestrated here; candidate
# enterprise search is not automatically invoked by this skill.
T_TREND = "recruitment_trend"
T_PROFILE = "recruitment_employer_profile"
T_DEMAND = "recruitment_demand_analysis"
T_SALARY = "recruitment_salary"
T_JOB_SEARCH = "recruitment_job_search"

# Explicit focus values are also exposed by the CLI for questions whose meaning
# cannot safely be resolved by keyword matching alone.
FOCUS_LABELS = {
    "trend": "招聘趋势", "profile": "雇主画像", "demand": "招聘需求",
    "salary": "职位薪酬", "jobs": "招聘职位", "city": "招聘城市",
}
FOCUS_PATTERNS = {
    "trend": r"趋势|走势|变化|节奏|活跃度|同比|环比|逐月|月度",
    "profile": r"画像|福利|雇主|招聘渠道|用工类型|用工形式",
    "demand": r"需求|职能|人才结构|岗位结构|职位结构|岗位类别|职位类别|岗位关键词|业务关键词",
    "salary": r"薪酬|薪资|薪水|月薪|年薪|工资|收入|薪金|(?<!福利)待遇",
    "jobs": r"职位明细|岗位明细|职位列表|岗位列表|职位检索|岗位检索|职位详情|岗位详情|"
            r"招聘职位|招聘岗位|前\s*[0-9一二两三四五六七八九十百千]+\s*条.{0,6}(?:职位|岗位)|"
            r"(?:在招|招聘|招募|招)(?:哪些|什么)(?:职位|岗位|人才|人)|"
            r"学历|教育要求|经验要求|工作经验|工作年限|应届|本科|硕士|博士|研究生|大专|专科|"
            r"(?:查看|查询|列出|展示|有哪些|抽取|检索).{0,12}(?:职位|岗位)(?!薪|工资|收入|待遇|需求|结构|类别|关键词|画像|级)",
    "city": r"城市|地域|地区|区域|工作地点|招聘地点|地理分布",
}
TOOL_LABELS = {
    T_TREND: "招聘趋势", T_PROFILE: "招聘画像", T_DEMAND: "招聘需求",
    T_SALARY: "职位薪酬", T_JOB_SEARCH: "职位检索",
}
PRODUCT_DETAILS = {"name": "招聘明细", "product_id": "66b338e274bf098447db7f09"}
PRODUCT_STATISTICS = {"name": "招聘统计", "product_id": "66b338e274bf098447db7f1b"}


def _requested_page_size(question: str) -> Optional[int]:
    match = re.search(r"前\s*([0-9]+|[一二两三四五六七八九十百千]+)\s*条", question or "")
    if not match:
        return None
    token = match.group(1)
    if token.isdigit():
        return int(token)
    digits = {"一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
    units = {"十": 10, "百": 100, "千": 1000}
    total = current = 0
    for char in token:
        if char in digits:
            current = digits[char]
        else:
            total += (current or 1) * units[char]
            current = 0
    return total + current


def _set_page_scope(plan: Dict[str, Any], page_size: int, sample_size: Optional[int] = None, max_pages: Optional[int] = None) -> None:
    if not 1 <= page_size <= 50:
        raise ValueError("page_size 必须在 1 到 50 之间")
    requested = _requested_page_size(plan["question"])
    target = sample_size if sample_size is not None else requested
    if target is not None and (isinstance(target, bool) or not isinstance(target, int) or target < 1):
        raise ValueError("sample_size 必须为正整数")
    automatic = max_pages is None
    filtered = any(plan.get(key) for key in ("city", "job_keyword", "date_start", "date_end"))
    if automatic:
        max_pages = max(1, (target + page_size - 1) // page_size) if target is not None and not filtered else 1
    if isinstance(max_pages, bool) or not isinstance(max_pages, int) or max_pages < 1:
        raise ValueError("max_pages 必须为正整数")
    plan.update(page_size=page_size, sample_size=target, max_pages=max_pages, pagination={},
                collection_mode="sample" if target is not None else "coverage",
                budget_basis="unfiltered_sample_target" if automatic and target is not None and not filtered
                else "initial_page" if automatic else "explicit_page_limit")
    goal = f"取得 {target} 条符合条件的记录" if target is not None else "按问题范围取得必要明细，不默认遍历全部历史记录"
    if any(t in plan["tools"] for t in (T_JOB_SEARCH, T_SALARY)) or (T_DEMAND in plan["tools"] and plan["view"] == "details"):
        plan.setdefault("collection_notes", []).append(f"付费明细采集计划：{goal}；单页 {page_size} 条、最多 {max_pages} 页。每次翻页均扣费，先按 total 计算数量，在既定调用预算内执行；页大小不是分析样本量。")


def _published_date(value: Any) -> Optional[dt.date]:
    """Accept dates/ISO datetimes, not guessed timestamps or incomplete dates."""
    text = str(value or "").strip()
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}(?:[T ].+)?", text):
        return None
    try:
        if len(text) == 10:
            return dt.date.fromisoformat(text)
        return dt.datetime.fromisoformat(text.removesuffix("Z") + "+00:00" if text.endswith("Z") else text).date()
    except ValueError:
        return None


def _months_before(day: dt.date, months: int) -> dt.date:
    year, month = divmod(day.year * 12 + day.month - 1 - months, 12)
    return dt.date(year, month + 1, min(day.day, calendar.monthrange(year, month + 1)[1]))


def _question_dates(question: str) -> tuple[str, str, List[str]]:
    """Infer only one clear window. Comparison windows need an explicit plan."""
    today = dt.date.today()
    iso_dates = re.findall(r"(?<!\d)\d{4}-\d{2}-\d{2}(?!\d)", question)
    if len(iso_dates) == 2 and re.search(r"至|到|~|～|—", question):
        return iso_dates[0], iso_dates[1], []
    pattern = (r"(?:最近|过去|近)(?:[0-9]+|[一二两三四五六七八九十百千]+|半)(?:个?月|天|周|年)"
               r"|今年|去年|(?<!\d)\d{4}年(?:\d{1,2}月(?:\d{1,2}日)?)?")
    periods = re.findall(pattern, question)
    if not periods and not iso_dates:
        return "", "", []
    warning = ["问题包含多个或未能可靠识别的时间范围，未自动按日期筛选；需用 --date-start / --date-end 明确单次分析窗口。"]
    if len(periods) != 1 or iso_dates:
        return "", "", warning
    token = periods[0]
    if token in ("今年", "去年"):
        year = today.year - int(token == "去年")
        end = today if token == "今年" else dt.date(year, 12, 31)
        return dt.date(year, 1, 1).isoformat(), end.isoformat(), []
    if re.fullmatch(r"\d{4}年", token) and not re.search(r"\d{4}年\s*(?:第|[一二三四1-4]季度|上半年|下半年|Q[1-4])", question, re.I):
        year = int(token[:4])
        if not 1 <= year <= 9999:
            return "", "", warning
        return dt.date(year, 1, 1).isoformat(), dt.date(year, 12, 31).isoformat(), []
    relative = re.fullmatch(r"(?:最近|过去|近)([0-9一二两三四五六七八九十百千]+|半)(个?月|天|周|年)", token)
    if not relative:
        return "", "", warning
    number, unit = relative.groups()
    if number == "半":
        if unit != "年":
            return "", "", warning
        start = _months_before(today, 6)
    else:
        count = _requested_page_size(f"前{number}条") or 0
        if count < 1:
            return "", "", warning
        try:
            start = (_months_before(today, count * (12 if unit == "年" else 1)) if unit in ("月", "个月", "年")
                     else today - dt.timedelta(days=count * (7 if unit == "周" else 1) - 1))
        except (ValueError, OverflowError):
            return "", "", warning
    return start.isoformat(), today.isoformat(), []


def _set_date_scope(plan: Dict[str, Any], date_start: str = "", date_end: str = "") -> None:
    paged = any(t in plan["tools"] for t in (T_JOB_SEARCH, T_SALARY)) or (T_DEMAND in plan["tools"] and plan["view"] == "details")
    if not (date_start or date_end):
        text = plan.get("intent_text", plan["question"])
        date_start, date_end, warnings = _question_dates(text)
        if paged:
            plan["warnings"].extend(warnings)
        else:
            other_period = re.search(r"季度|上半年|下半年|本月|本周|上月|上周|本季度|本年度|本年|本日|今天|昨天|去年|历年", text)
            native_trend_period = (plan["topics"] == ["trend"] and not warnings and not other_period
                                   and re.search(r"(?:最近|过去|近)(?:三|3)个?月", text))
            if (date_start or date_end or warnings or other_period) and not native_trend_period:
                plan["warnings"].append("所选企业汇总不支持所问时间范围，未按发布日期筛选；趋势接口仅提供当前和近三个月汇总。")
            date_start = date_end = ""
    for value in (date_start, date_end):
        if value and (not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value) or _published_date(value) is None):
            raise ValueError("日期必须为有效的 YYYY-MM-DD")
    if date_start and date_end and date_start > date_end:
        raise ValueError("date_start 不能晚于 date_end")
    plan.update(date_start=date_start, date_end=date_end)
    if date_start or date_end:
        plan["warnings"].append(
            f"请求发布日期范围：{date_start or '不限起日'} 至 {date_end or '不限止日'}（含边界）。"
            "上游不支持日期筛选且未承诺排序，仅对已读取明细本地过滤；缺失或无法解析日期的记录不纳入该窗口，企业汇总仍保持原口径。")
        if not paged:
            plan["warnings"].append("本次仅查询企业汇总，未查询职位明细，不能应用上述发布日期窗口；趋势接口仍仅为当前和近三个月口径。")
    elif paged:
        plan["warnings"].append("未指定可识别的单一日期窗口，明细按数据源可用时期采集，未擅自限定为最近90天等时间范围。")


def _question_constraints(question: str, enterprise: str, city: str, job_keyword: str) -> tuple[str, str, List[str]]:
    """Recognize only unambiguous common examples; callers may pass explicit filters."""
    if not question:
        return city.strip(), job_keyword.strip(), []
    text = question.replace(enterprise, "") if enterprise else question
    city_names = ("北京", "上海", "广州", "深圳", "杭州", "南京", "苏州", "成都", "重庆", "武汉", "天津", "西安",
                  "长沙", "合肥", "郑州", "青岛", "济南", "宁波", "厦门", "福州", "东莞", "佛山", "无锡", "珠海",
                  "沈阳", "大连", "哈尔滨", "长春", "昆明", "贵阳", "南宁", "海口", "石家庄", "太原", "南昌")
    found = []
    for match in re.finditer("|".join(city_names), text):
        prefix = text[max(0, match.start() - 5):match.start()]
        if not re.search(r"不在|不要|排除|不含|不包括", prefix) and match.group() not in found:
            found.append(match.group())
    warnings = []
    if not city and len(found) == 1:
        city = found[0]
    elif not city and len(found) > 1:
        warnings.append("问题涉及多个城市，未对城市做单一筛选；本次累计样本不能代表完整城市比较。")
    if not job_keyword:
        role_text = text
        for location in found:
            role_text = re.sub(re.escape(location) + "市?", "", role_text)
        role_text = re.sub(r"^(?:请|帮我|我想|只想|希望|需要|想|只|看一下|看看|查看|查询|分析|了解|查|找|看)+", "", role_text).lstrip("的 ")
        pattern = (r"(?:^|招聘|招募|招|查看|查询|分析|了解|哪些|寻找|找|的|针对)\s*"
                   r"([A-Za-z0-9\u4e00-\u9fff+#]{0,12}(?:工程师|程序员|开发|架构师|分析师|研究员|设计师|经理|会计|销售))"
                   r"(?=薪|工资|职位|岗位|需求|待遇|招聘|的|在|[，,。？?]|$)")
        roles = []
        for match in re.finditer(pattern, role_text):
            role = match.group(1).lstrip("的")
            prefix = role_text[max(0, match.start() - 5):match.start()]
            if not re.search(r"公司|企业|不要|不需要|不看|排除|无需", role + prefix):
                roles.append(role)
        roles = list(dict.fromkeys(roles))
        if len(roles) == 1:
            job_keyword = roles[0]
        elif len(roles) > 1:
            warnings.append("问题涉及多个职位名称，未对职位做单一筛选；本次累计样本不能代表完整职位比较。")
    return city.strip(), job_keyword.strip(), warnings


def _focus_plan(question: str, focus: Optional[Sequence[str]], view: str,
                city: str, job_keyword: str, subject_name: str = "") -> Dict[str, Any]:
    """Choose an ordered union of requested dimensions, not one generic template."""
    question = (question or "").strip()
    intent_text = question.replace(subject_name, "") if subject_name else question
    excluded: List[str] = []
    if focus:
        topics = list(dict.fromkeys(focus))
    else:
        found = []
        for topic, pattern in FOCUS_PATTERNS.items():
            for match in re.finditer(pattern, intent_text, flags=re.IGNORECASE):
                # Do not turn "不需要趋势" into an additional paid query.
                prefix = re.split(r"[，,。；;、]|但是|但|不过|而是", intent_text[:match.start()])[-1]
                suffix = intent_text[match.end():match.end() + 3]
                if re.search(r"不要|不需要|无需|不看|排除|不用", prefix) or re.match(r"(?:不要|不需要|无需)", suffix):
                    if topic not in excluded:
                        excluded.append(topic)
                    continue
                found.append((match.start(), topic))
                break
        # A period modifying a salary/jobs question is a filter, not a separate
        # request to buy the trend product. Keep the terse trend-only shorthand.
        if not found and "trend" not in excluded:
            period = re.search(r"近[三3]个?月", intent_text)
            if period:
                found.append((period.start(), "trend"))
        is_full = not question or bool(re.search(r"全维度|全量|全面|综合招聘|完整招聘", intent_text))
        topics = list(dict.fromkeys(topic for _, topic in sorted(found)))
        if not is_full and not topics and (city or job_keyword) and "jobs" not in excluded:
            topics = ["jobs"]
        elif is_full or not topics:
            topics = [topic for topic in FOCUS_LABELS if topic not in excluded] if excluded else ["full"]
        else:
            topics = [topic for topic in topics if topic not in excluded]
    if "full" in topics:
        topics = ["full"]
    elif (city or job_keyword) and "jobs" not in excluded and not any(t in topics for t in ("salary", "jobs", "city")):
        topics.append("jobs")

    # A question explicitly asking for job-level demand wins over the generic
    # statistics default. No extra statistics call is hidden behind this view.
    if "demand" in topics and re.search(r"岗位级|职位级|需求明细|需求详情", intent_text):
        view = "details"
    tools: List[str] = []
    for topic in (list(FOCUS_LABELS) if topics == ["full"] else topics):
        # Salary rows already carry the city; no second details call is needed
        # just to group those same returned rows geographically.
        if topic == "city" and "salary" in topics and "jobs" not in topics:
            continue
        tool = {"trend": T_TREND, "profile": T_PROFILE, "demand": T_DEMAND,
                "salary": T_SALARY, "jobs": T_JOB_SEARCH, "city": T_JOB_SEARCH}[topic]
        if tool not in tools:
            tools.append(tool)
    warnings = []
    if re.search(r"同比|环比|逐月|月度|按月|历年|历史序列", intent_text):
        warnings.append("趋势接口仅提供当前及近三个月汇总，不提供逐月序列，无法计算同比或环比。")
    if re.search(r"年薪|年收入", intent_text):
        warnings.append("职位薪酬为所返回的月薪区间，不能据此计算或承诺年薪。")
    if re.search(r"(?:高于|低于|超过|不少于|至少|大于|小于)\s*[0-9]|[0-9]+\s*[kK万千]?(?:以上|以下)", intent_text):
        warnings.append("本报告未按薪酬阈值筛选；薪酬明细仅为本次累计样本。")
    if re.search(r"本科|硕士|博士|研究生|大专|专科|应届|[一二三四五六七八九十0-9]+年(?:以上|以下|工作经验)", intent_text):
        warnings.append("未按指定学历或经验门槛筛选；学历和年限分布仅描述返回的本次累计样本。")
    if city or job_keyword:
        warnings.append("城市及职位关键词仅在本次累计取得的职位样本中筛选；企业整体统计不受筛选条件约束。")
        if not any(tool in tools for tool in (T_SALARY, T_JOB_SEARCH)) and not (T_DEMAND in tools and view == "details"):
            warnings.append("所选范围没有职位明细，无法应用该筛选条件。")
    return {"question": question, "intent_text": intent_text, "topics": topics, "tools": tools, "view": view,
            "city": city.strip(), "job_keyword": job_keyword.strip(), "warnings": warnings, "excluded": excluded}


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _is_empty_response(value: Any) -> bool:
    if value is None or value == "" or value == {}:
        return True
    if isinstance(value, str):
        text = value.strip().lower()
        return any(token in text for token in ("查询数据为空", "暂无数据", "未查询到", "未检索到", "no data"))
    if isinstance(value, dict):
        if (value.get("isError") is True or value.get("is_error") is True
                or value.get("success") is False or value.get("_error") not in (None, "", False)):
            return False
        # Gateway code 10001 is an explicit empty-data result, including when
        # the MCP exposes it in an {error, code} envelope rather than a list.
        if value.get("code") in (10001, "10001"):
            return True
        for key in ("text", "message", "msg"):
            if key in value and _is_empty_response(value.get(key)):
                return True
        containers = [value.get(key) for key in ("resultList", "list", "items", "data") if key in value]
        if containers and all(item in (None, [], {}) for item in containers):
            total = value.get("total")
            return total in (None, 0, "0")
    return False


def _is_api_error(value: Any) -> bool:
    """Return True only for failed calls; platform empty-data text is not an error."""
    if value is None or _is_empty_response(value):
        return False
    if isinstance(value, str):
        text = value.lower()
        return any(token in text for token in (
            "接口调用失败", "查询失败", "状态码：4", "状态码：5",
            "upstream timeout", "tool failed", "unauthorized", "forbidden",
        ))
    if isinstance(value, dict):
        if value.get("isError") is True or value.get("is_error") is True or value.get("success") is False:
            return True
        if any(value.get(key) not in (None, "", False) for key in ("_error", "error")):
            return True
        code = value.get("code")
        if code not in (None, 0, "0", 200, "200", 10001, "10001"):
            return True
        return any(_is_api_error(value.get(key)) for key in ("text", "message", "msg") if key in value)
    return False


def _first_list(value: Any) -> List[Any]:
    if _is_api_error(value) or _is_empty_response(value):
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        for key in ("resultList", "list", "items"):
            if isinstance(value.get(key), list):
                return value[key]
        nested = value.get("data")
        if isinstance(nested, list):
            return nested
        if isinstance(nested, dict):
            return _first_list(nested)
    return []


def _first_record(value: Any) -> Dict[str, Any]:
    if _is_api_error(value) or _is_empty_response(value):
        return {}
    for record in _first_list(value):
        if isinstance(record, dict) and _has_evidence(record):
            return record
    if isinstance(value, dict):
        envelope = {"resultList", "list", "items", "data", "total", "pageNo", "pageSize", "text", "message", "msg", "code"}
        if not set(value).issubset(envelope) and _has_evidence(value):
            return value
    return {}


def _has_evidence(value: Any) -> bool:
    if value is None or value == "" or value == "-":
        return False
    if _is_api_error(value) or _is_empty_response(value):
        return False
    if isinstance(value, dict):
        return any(_has_evidence(item) for key, item in value.items() if key not in {"total", "pageNo", "pageSize"})
    if isinstance(value, (list, tuple, set)):
        return any(_has_evidence(item) for item in value)
    return True


def _meaningful_row(row: Mapping[str, Any]) -> bool:
    return any(_has_evidence(value) for value in row.values())


def _attach_call_status(report: Dict[str, Any], calls: Mapping[str, Any]) -> Dict[str, Any]:
    """Disclose failed and genuine-empty domains without exposing upstream details."""
    failed = [name for name, payload in calls.items() if _is_api_error(payload)]
    empty = [name for name, payload in calls.items() if not _is_api_error(payload) and _is_empty_response(payload)]
    source = report.setdefault("data_source", {})
    source["failed_products"] = failed
    source["empty_products"] = empty
    return report


def _apply_resolution_limit(report: Dict[str, Any], resolved: Mapping[str, Any]) -> Dict[str, Any]:
    subject = report.setdefault("subject", {})
    subject["resolved"] = False
    subject["requires_confirmation"] = True
    subject["resolve_reason"] = resolved.get("reason", "主体未唯一确认")
    subject["candidate_sample"] = list(resolved.get("candidate_sample") or [])
    if resolved.get("fuzzy_total") is not None:
        subject["fuzzy_total"] = resolved.get("fuzzy_total")
    message = "输入未唯一确认到特定企业；已停止主体专属数据调用，不生成该企业的经营、风险或舆情评价。请使用候选企业全称或企业标识重试。"
    report["abstract"] = message
    report["summary"] = message
    report["executive_summary"] = [message]
    report["metrics"] = []
    report["representative_records"] = []
    report["insights"] = [{"feature": "主体确认受限", "evidence": subject["resolve_reason"], "interpretation": message}]
    report.setdefault("data_source", {})["subject_resolution"] = "confirmation_required"
    return report


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


def _count_text(value: Any) -> str:
    """Render whole-number counts without a trailing ``.0`` from numeric APIs."""
    if isinstance(value, bool):
        return _text(value)
    if isinstance(value, (int, float)):
        number = float(value)
        return str(int(number)) if number.is_integer() else _text(value)
    if isinstance(value, str) and re.fullmatch(r"\d+\.0+", value.strip()):
        return value.strip().split(".")[0]
    return _text(value)


def _int(value: Any) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _safe_call(tool: str, arguments: Dict[str, Any]) -> Any:
    try:
        result = call_tool_once(mcp_client.call_tool, tool, arguments)
        if _is_api_error(result):
            return {"_error": "API错误"}
        return result
    except Exception as exc:
        return {"_error": str(exc)}


def _safe_total(payload: Any) -> Any:
    if isinstance(payload, dict):
        if _is_api_error(payload):
            return None
        value = payload.get("total")
        if value is not None and not isinstance(value, bool) and re.fullmatch(r"\d+", str(value)):
            return int(value)
        if isinstance(payload.get("data"), dict):
            return _safe_total(payload["data"])
    return None


def _salary_text(value: Any) -> str:
    """workingSalary 实际结构：{coinType, min, max}（数值型，单位元/月）。

    渲染为紧凑的 "min-max" 形式（千元单位），方便在表格中阅读。
    """
    if isinstance(value, dict):
        lo = value.get("min")
        hi = value.get("max")
        currency = _text(value.get("coinType") or value.get("currency"))
        if lo is not None or hi is not None:
            lo_s = f"{_num_k(lo)}K" if _is_num(lo) else _text(lo)
            hi_s = f"{_num_k(hi)}K" if _is_num(hi) else _text(hi)
            suffix = ("（币种未注明）" if not currency else f"（币种：{currency}）"
                      if currency.upper() not in ("CNY", "RMB", "人民币", "¥") else "")
            interval = f"{lo_s}-{hi_s}" if lo is not None and hi is not None else f"≥{lo_s}" if lo is not None else f"≤{hi_s}"
            return f"{interval}{suffix}"
        if value.get("origin"):
            original = _text(value["origin"])
            if currency:
                return (f"{original} 人民币" if currency.upper() in ("CNY", "RMB", "人民币", "¥")
                        else f"{original}（币种：{currency}）")
            return _salary_text(original)
    original = _text(value)
    currency_pattern = r"CNY|RMB|人民币|¥|元|USD|JPY|KRW|CAD|AUD|GBP|EUR|HKD|CHF|SGD|TWD|\$|英镑|欧元"
    if re.search(r"\d", original) and not re.search(currency_pattern, original, re.I):
        return f"{original}（币种未注明）"
    return original


def _money_per_month(value: Any) -> str:
    if _is_num(value):
        return f"{float(value):,.0f} 元/月"
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
    if isinstance(value, dict):
        currency = _text(value.get("coinType") or value.get("currency"))
        if not currency or currency.upper() not in ("CNY", "RMB", "人民币", "¥"):
            return None
        lo = value.get("min") if value.get("min") is not None else value.get("minSalary")
        hi = value.get("max") if value.get("max") is not None else value.get("maxSalary")
        lo_f = _to_float(lo)
        hi_f = _to_float(hi)
        if lo_f is not None and hi_f is not None:
            mid = (lo_f + hi_f) / 2.0
            return mid / 1000.0 if mid >= 1000 else mid
        return None
    s = str(value or "").strip()
    if not s or re.search(r"币种未注明|币种：|[≥≤]|以上|以下|起薪|日薪|时薪|周薪|年薪|/天|/日|/小时|/年|美元|港元|欧元|日元|韩元|加元|澳元|英镑|瑞郎|新元|台币|USD|HKD|EUR|JPY|KRW|CAD|AUD|GBP|CHF|SGD|TWD|\$", s, re.I):
        return None
    # Only the first salary amount/range belongs to the monthly pay. A later
    # "·14薪" describes payment months, not another amount in that range.
    match = re.search(r"(\d+(?:\.\d+)?)\s*[kK千]?\s*(?:[-~～至]\s*(\d+(?:\.\d+)?)\s*[kK千]?)?", s)
    if not match:
        return None
    vals = [float(n) for n in match.groups() if n is not None]
    mid = sum(vals) / len(vals)
    if "万" in s:
        mid *= 10
    elif mid >= 1000:
        mid = mid / 1000.0
    return mid


def _to_float(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _salary_dist_rows(rows: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
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


def _city_dist_rows(rows: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
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


def _add_job_requirements(row: Dict[str, Any], item: Mapping[str, Any]) -> None:
    education = item.get("recruitingEducation")
    if isinstance(education, (str, int, float)) and str(education).strip():
        row["学历要求"] = _text(education)
    seniority = item.get("workingSeniority")
    if isinstance(seniority, dict):
        low, high = seniority.get("min"), seniority.get("max")
        if low is not None and high is not None:
            row["工作年限"] = f"{_text(low)}–{_text(high)} 年" if low != high else f"{_text(low)} 年"
        elif low is not None:
            row["工作年限"] = f"{_text(low)} 年及以上"
        elif high is not None:
            row["工作年限"] = f"不超过 {_text(high)} 年"
    elif isinstance(seniority, (str, int, float)) and str(seniority).strip():
        row["工作年限"] = _text(seniority)


def _requirement_dist(rows: Sequence[Mapping[str, Any]], key: str) -> List[Dict[str, Any]]:
    counts: Dict[str, int] = {}
    for row in rows:
        value = row.get(key)
        if value not in (None, "", "-"):
            name = str(value)
            counts[name] = counts.get(name, 0) + 1
    return [{key: name, "记录数": str(count)} for name, count in
            sorted(counts.items(), key=lambda item: (-item[1], item[0]))]


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

def resolve_enterprise_name(raw: str, keyword_type: str = "name") -> Dict[str, Any]:
    """Do not silently associate an ambiguous short name with a legal entity."""
    raw = (raw or "").strip()
    if not raw:
        return {"keyword": "", "enterprise": "", "resolved": False, "requires_confirmation": True, "reason": "关键词为空", "candidate_sample": []}
    if keyword_type in ("nameId", "regNumber", "socialCreditCode"):
        return {"keyword": raw, "enterprise": raw, "resolved": True, "requires_confirmation": False, "reason": "用户提供企业标识", "candidate_sample": []}
    if any(suffix in raw for suffix in ("公司", "有限", "院", "厂", "中心", "事务所", "合作社", "合伙")):
        return {"keyword": raw, "enterprise": raw, "resolved": True, "requires_confirmation": False, "reason": "用户提供企业全称", "candidate_sample": []}
    return {"keyword": raw, "enterprise": raw, "resolved": False, "requires_confirmation": True, "reason": "短名称未唯一确认，本报告不会自动归属企业主体", "candidate_sample": []}


def _derive_core_metrics(metrics: List[Dict[str, Any]], core: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """Derive additional metrics from core analysis sections."""
    city_dist = core.get("city_dist", []) if isinstance(core, dict) else []
    source_dist = core.get("source_dist", []) if isinstance(core, dict) else []
    salary_dist = core.get("salary_dist", []) if isinstance(core, dict) else []
    if isinstance(city_dist, list) and city_dist:
        metrics.append({"label": "本次样本城市数", "value": str(len(city_dist)), "hint": "本次返回明细样本覆盖的去重城市数，并非全部岗位城市总数"})
        try:
            nums = [int(str(r.get("岗位数", "0")).replace(",", "")) for r in city_dist if str(r.get("岗位数", "0")).replace(",", "").isdigit()]
            total = sum(nums)
            if total > 0:
                top3 = sum(sorted(nums, reverse=True)[:3])
                metrics.append({"label": "城市CR3", "value": f"{top3/total*100:.1f}%", "hint": f"在有城市信息的 {total} 条记录中，前3大城市的记录集中度；不含城市缺失记录"})
        except (ValueError, TypeError):
            pass
    if isinstance(source_dist, list) and source_dist:
        metrics.append({"label": "画像返回渠道数", "value": str(len(source_dist)), "hint": "画像渠道列表中的去重渠道数，并非职位数量"})
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
    metrics.append({"label": "当前招聘人数", "value": _count_text(cur) or "-", "hint": "当前在招岗位人数"})
    metrics.append({"label": "近三月招聘人数", "value": _count_text(last3) or "-", "hint": "近三个月招聘人数；与当前值为不同时间口径"})
    metrics.append({"label": "近三月岗位数", "value": _count_text(t.get("recruitingLastThreeMonthNo")) or "-", "hint": "近三月发布岗位数"})
    avg_update = t.get("recruitingAvgUpdate")
    metrics.append({"label": "平均更新频率", "value": (f"{_text(avg_update)} 秒" if avg_update is not None else "-"), "hint": "岗位平均更新频率（上游单位：秒）"})
    avg_salary = t.get("recruitingAvgWorkingSalary")
    avg_salary_text = _money_per_month(avg_salary) or "-"
    metrics.append({"label": "平均薪酬", "value": avg_salary_text, "hint": "在招岗位平均薪酬（元/月）"})
    if job_search_total is not None:
        metrics.append({"label": "职位检索命中总数", "value": str(job_search_total) + " 条", "hint": "企业职位检索返回的总记录数，不等同于当前在招人数"})
    return [m for m in metrics if m.get("value") not in ("", None, "-")]


def build_caliber(subject: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "match_target": subject.get("enterprise") or subject.get("match_raw"),
        "match_type": "按已确认的企业名称或企业标识匹配；简称不能自动归属为某一主体",
        "data_scope": "招聘趋势概览、雇主招聘画像、招聘需求分析、职位薪酬明细、招聘职位明细",
        "products": ["招聘明细", "招聘统计"],
        "limit": "数据来自招聘公开数据；少量字段可能存在更新延迟。",
    }


def build_core_analysis(trend: Any, profile: Any, demand_stats: Any, salary: Any, job_search: Any,
                        demand_view: str = "statistics") -> Dict[str, Any]:
    p = profile if isinstance(profile, dict) else {}
    t = trend if isinstance(trend, dict) else {}
    ds = demand_stats if isinstance(demand_stats, dict) and demand_view == "statistics" else {}

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
            profile_kv[label] = (_money_per_month(src.get(k)) if k == "recruitingAvgWorkingSalary"
                                 else _count_text(src.get(k)) if k != "recruitingAvgUpdate"
                                 else _text(src.get(k)))
    # 福利标签 / 城市列表 / 渠道 / 用工类型 / 业务关键词：profile 优先，回退 demand 统计视图。
    def _first_list_str(src: Mapping[str, Any], keys: Sequence[str]) -> List[str]:
        for k in keys:
            v = src.get(k)
            if isinstance(v, list) and v:
                return [str(x) for x in v if x]
        return []

    benefit_source = next((src[key] for src in (p, ds) for key in ("benefitList", "welfareList")
                           if src.get(key) not in (None, "", [])), [])
    benefit_data = organize_benefits(benefit_source)
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
        profile_kv["画像地点标签数"] = str(len(city_dedup))
        profile_kv["地点标签（前10项）"] = "、".join(city_dedup[:10]) + ("…" if len(city_dedup) > 10 else "")
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
            demand_kv[label] = (_money_per_month(ds.get(k)) if k == "recruitingAvgWorkingSalary"
                                else _count_text(ds.get(k)))
    if biz_kw:
        demand_kv["业务关键词"] = "、".join(biz_kw)
    if pos_kw:
        demand_kv["岗位关键词"] = "、".join(pos_kw)

    # 招聘趋势（汇总指标，非时间序列）。
    trend_rows = [row for row in [
        {"指标": "当前招聘人数", "数值": _count_text(t.get("recruitingCurrentCount")) or "-"},
        {"指标": "近三月招聘人数", "数值": _count_text(t.get("recruitingLastThreeMonthCount")) or "-"},
        {"指标": "近三月岗位数", "数值": _count_text(t.get("recruitingLastThreeMonthNo")) or "-"},
        {"指标": "岗位平均更新频率(秒)", "数值": _text(t.get("recruitingAvgUpdate")) or "-"},
        {"指标": "平均薪酬", "数值": _money_per_month(t.get("recruitingAvgWorkingSalary")) or "-"},
    ] if row["数值"] != "-"]

    salary_total = _safe_total(salary)
    salary_rows = []
    for item in _first_list(salary):
        if not isinstance(item, dict):
            continue
        row = {
            "职位": _text(item.get("recruitingName")) or "-",
            "城市": _text(item.get("recruitingCity")) or "-",
            "渠道": _text(item.get("recruitingSource")) or "-",
            "薪酬": _salary_text(item.get("workingSalary")) or "-",
            "发布日期": _text(item.get("recruitingPublishedTime")) or "-",
        }
        if _meaningful_row(row):
            salary_rows.append(row)

    job_total = _safe_total(job_search)
    job_rows = []
    for item in _first_list(job_search):
        if not isinstance(item, dict):
            continue
        row = {
            "职位名称": _text(item.get("recruitingName")) or "-",
            "城市": _text(item.get("recruitingCity")) or "-",
            "渠道": _text(item.get("recruitingSource")) or "-",
            "薪酬": _salary_text(item.get("workingSalary")) or "-",
            "发布日期": _text(item.get("recruitingPublishedTime")) or "-",
        }
        _add_job_requirements(row, item)
        if _meaningful_row(row):
            job_rows.append(row)

    # 派生：薪酬区间分布（聚合 salary_records，回退 job_records）
    salary_src = salary_rows if salary_rows else job_rows
    salary_dist_rows = _salary_dist_rows(salary_src)
    # 两个工具常返回同一页岗位；优先职位检索页，缺失时才回退薪酬页，避免重复计数。
    city_pool = list(job_rows) if job_rows else list(salary_rows)
    city_dist_rows = _city_dist_rows(city_pool)
    # 渠道仅是列表，不能伪造每个渠道的岗位数或集中度。
    source_dist_rows = source_dedup
    # tags 段
    position_tags = pos_kw

    demand_rows = []
    if demand_view == "details":
        for item in _first_list(demand_stats):
            if not isinstance(item, dict):
                continue
            row = {
                "职位名称": _text(item.get("recruitingName")) or "-",
                "城市": _text(item.get("recruitingCity")) or "-",
                "渠道": _text(item.get("recruitingSource")) or "-",
                "薪酬": _salary_text(item.get("workingSalary")) or "-",
                "发布日期": _text(item.get("recruitingPublishedTime")) or "-",
            }
            _add_job_requirements(row, item)
            if _meaningful_row(row):
                demand_rows.append(row)
    if not job_rows and not salary_rows and demand_rows:
        salary_dist_rows = _salary_dist_rows(demand_rows)
        city_dist_rows = _city_dist_rows(demand_rows)

    title_counts: Dict[str, int] = {}
    for row in job_rows or demand_rows:
        name = row.get("职位名称")
        if name and name != "-":
            title_counts[name] = title_counts.get(name, 0) + 1
    title_dist = [{"职位名称": name, "记录数": str(count)} for name, count in
                  sorted(title_counts.items(), key=lambda item: (-item[1], item[0]))]
    requirement_rows = job_rows or demand_rows
    education_dist = _requirement_dist(requirement_rows, "学历要求")
    seniority_dist = _requirement_dist(requirement_rows, "工作年限")
    city_salaries: Dict[str, List[float]] = {}
    for row in salary_rows or job_rows or demand_rows:
        city_name = row.get("城市")
        midpoint = _salary_mid_k(row.get("薪酬"))
        if city_name and city_name != "-" and midpoint is not None:
            city_salaries.setdefault(city_name, []).append(midpoint)
    salary_by_city = [{"城市": name, "可解析样本数": str(len(values)),
                       "薪酬区间中点均值": f"{sum(values) / len(values):.1f}K/月"}
                      for name, values in city_salaries.items()]
    demand_columns = [("职位名称", "职位名称"), ("城市", "城市"), ("渠道", "渠道"), ("薪酬", "薪酬")]
    job_columns = list(demand_columns)
    for key in ("学历要求", "工作年限"):
        if any(key in row for row in demand_rows):
            demand_columns.append((key, key))
        if any(key in row for row in job_rows):
            job_columns.append((key, key))
    demand_columns.append(("发布日期", "发布日期"))
    job_columns.append(("发布日期", "发布日期"))

    consistency_check: Dict[str, Any] = {}
    current_count = _int(t.get("recruitingCurrentCount"))
    job_total_int = _int(job_total)
    if current_count is not None and job_total_int is not None:
        consistency_check = {
            "趋势视图当前招聘人数": current_count,
            "职位检索命中总数": job_total_int,
            "核验结论": "当前招聘人数与职位检索记录总数口径不同，数值相同或不同均不能推断冲突，须分别解读，不得互相替代",
        }

    sections = [
        {"key": "employer_profile", "title": "雇主招聘画像", "kind": "kv",
         "note": "地点字段可能包含别名、区县或地标，仅作来源标签，不视为去重行政城市数"},
        {"key": "demand_stats", "title": "招聘需求统计", "kind": "kv", "note": "基于招聘统计视图的企业级汇总"},
        *benefit_sections(benefit_data),
        {"key": "position_keywords", "title": "岗位关键词", "kind": "tags", "note": "统计视图返回的关键词，不代表岗位数量排名"},
        {"key": "source_dist", "title": "招聘渠道", "kind": "tags", "note": "画像返回的渠道列表，不包含各渠道岗位数量"},
        {"key": "salary_dist", "title": "薪酬区间分布", "kind": "bar", "note": "按本次累计样本可解析的薪酬区间中点聚合，不代表全部岗位",
         "chart": {"name": "薪酬区间", "value": "岗位数", "orient": "v"},
         "columns": [("薪酬区间", "薪酬区间"), ("岗位数", "岗位数")]},
        {"key": "city_dist", "title": "招聘城市分布", "kind": "bar", "note": "仅按本次累计职位样本中城市已知的记录聚合，城市缺失记录不计入；不代表全部岗位",
         "chart": {"name": "城市", "value": "岗位数", "orient": "h"},
         "columns": [("城市", "城市"), ("岗位数", "岗位数")]},
        {"key": "trend_overview", "title": "招聘趋势", "kind": "table", "note": "招聘趋势概览（汇总指标，非逐月时间序列）",
         "columns": [("指标", "指标"), ("数值", "数值")]},
        {"key": "consistency_check", "title": "招聘数量口径核验", "kind": "kv", "note": "对比趋势视图与职位检索产品，不将不同口径强行合并"},
        {"key": "title_dist", "title": "职位名称分布", "kind": "bar", "note": "仅按本次累计样本中的原始职位名称统计，不推断职能分类",
         "chart": {"name": "职位名称", "value": "记录数", "orient": "h"},
         "columns": [("职位名称", "职位名称"), ("记录数", "记录数")]},
        {"key": "education_dist", "title": "学历要求分布", "kind": "bar", "note": "按本次累计样本中原样返回的学历要求统计，缺失学历的记录不计入",
         "chart": {"name": "学历要求", "value": "记录数", "orient": "h"},
         "columns": [("学历要求", "学历要求"), ("记录数", "记录数")]},
        {"key": "seniority_dist", "title": "工作年限要求分布", "kind": "bar", "note": "按本次累计样本中返回的年限区间统计，缺失年限的记录不计入",
         "chart": {"name": "工作年限", "value": "记录数", "orient": "h"},
         "columns": [("工作年限", "工作年限"), ("记录数", "记录数")]},
        {"key": "salary_by_city", "title": "城市薪酬样本", "kind": "table", "note": "本次样本中可解析岗位薪酬区间中点的简单均值，不代表各城市整体薪酬水平",
         "columns": [("城市", "城市"), ("可解析样本数", "可解析样本数"), ("薪酬区间中点均值", "薪酬区间中点均值")]},
        {"key": "demand_details", "title": "岗位需求明细", "kind": "table", "note": f"本次累计返回 {len(demand_rows)} 条岗位需求记录",
         "columns": demand_columns},
        {"key": "salary_records", "title": "职位薪酬明细", "kind": "table", "note": f"累计展示 {len(salary_rows)} 条" + (f"；企业明细总数 {salary_total} 条" if salary_total is not None else ""),
         "columns": [("职位", "职位"), ("城市", "城市"), ("渠道", "渠道"), ("薪酬", "薪酬"), ("发布日期", "发布日期")]},
        {"key": "job_records", "title": "招聘职位明细", "kind": "table", "note": f"累计展示 {len(job_rows)} 条" + (f"；企业明细总数 {job_total} 条" if job_total is not None else ""),
         "columns": job_columns},
    ]

    return {
        "sections": sections,
        "employer_profile": profile_kv,
        "demand_stats": demand_kv,
        **benefit_data,
        "position_keywords": position_tags,
        "source_dist": source_dist_rows,
        "salary_dist": salary_dist_rows,
        "city_dist": city_dist_rows,
        "trend_overview": trend_rows,
        "consistency_check": consistency_check,
        "title_dist": title_dist,
        "education_dist": education_dist,
        "seniority_dist": seniority_dist,
        "salary_by_city": salary_by_city,
        "demand_details": demand_rows,
        "salary_records": salary_rows,
        "job_records": job_rows,
    }


def build_records(core: Mapping[str, Any]) -> List[Dict[str, Any]]:
    out = []
    for item in core.get("job_records") or core.get("demand_details") or core.get("salary_records") or []:
        row = {
            "职位名称": item.get("职位名称") or item.get("职位") or "-",
            "城市": item.get("城市") or "-",
            "发布日期": item.get("发布日期") or "-",
        }
        if "薪酬" in item:
            row["薪酬"] = item.get("薪酬") or "-"
        for key in ("学历要求", "工作年限"):
            if key in item:
                row[key] = item[key]
        out.append(row)
    return out[:20]


def build_insights(subject: Mapping[str, Any], core: Mapping[str, Any], metrics: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    insights: List[Dict[str, Any]] = []
    metric_map = {m["label"]: str(m["value"]) for m in metrics}
    cur = metric_map.get("当前招聘人数")
    last3 = metric_map.get("近三月招聘人数")
    avg = metric_map.get("平均薪酬")

    if cur:
        insights.append({
            "feature": "招聘规模",
            "evidence": f"当前在招人数 {cur}。",
            "interpretation": "该值仅表示数据源当前记录的招聘人数；需结合历史序列和人员净增减后再判断扩张状态。",
        })
    if last3:
        insights.append({
            "feature": "近三月招聘汇总",
            "evidence": f"近三月招聘人数 {last3}。",
            "interpretation": "该值是近三月汇总，与当前值的时间口径不同；不提供逐月变化，不能据此判断招聘节奏或业务扩张。",
        })
    # 薪酬区间集中度
    salary_dist = core.get("salary_dist") or []
    if salary_dist:
        conc = _concentration(salary_dist, "薪酬区间", "岗位数", 1)
        if conc:
            insights.append({
                "feature": "薪酬带集中度",
                "evidence": f"“{conc['top']}”区间岗位占比约 {conc['top_share']:.0f}%。",
                "interpretation": "该分布仅描述已返回岗位样本的薪酬区间，不能据此推断整体岗位类型或团队结构。",
            })
    # 平均薪酬换算（K 中位）— salary/job 行已渲染为 "薪酬": "min-max" 字符串。
    salary_rows = core.get("salary_records") or []
    job_rows = core.get("job_records") or []
    sample = salary_rows or (job_rows if "salary_dist" in core or "salary_by_city" in core else [])
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
            "evidence": f"样本岗位薪酬区间中点的均值约 {avg_mid:.0f}K/月（n={len(mids)}）。",
                "interpretation": "该样本均值描述已返回岗位的薪酬区间，不代表整体人才竞争力或岗位结构。",
        })
    elif avg and avg != "-":
        insights.append({
            "feature": "薪酬水平",
            "evidence": f"在招岗位平均薪酬 {avg}。",
            "interpretation": "平均薪酬仅描述数据源返回口径；需有同地区同岗位基准后才能比较竞争力。",
        })
    benefits = core.get("benefit_tags") or []
    if benefits:
        insights.append({
            "feature": "画像福利标签",
            "evidence": f"来源标签经拆分、去重与分类后，识别 {len(benefits)} 项福利/工作安排线索，包括{'、'.join(map(str, benefits[:3]))}。",
            "interpretation": "薪资、任职条件和企业/岗位宣传已单列，不计入福利；保留原文与分类依据，不能推定全员享有或当前有效。",
        })
    keywords = core.get("position_keywords") or []
    if keywords:
        insights.append({
            "feature": "岗位关键词",
            "evidence": f"统计视图返回的关键词包括{'、'.join(map(str, keywords[:5]))}。",
            "interpretation": "关键词不附岗位数量，不能当作职能分布或招聘热度排名。",
        })
    jobs = core.get("job_records") or core.get("demand_details") or []
    if jobs:
        names = [str(row.get("职位名称")) for row in jobs if row.get("职位名称") not in (None, "", "-")]
        evidence = f"本次累计展示 {len(jobs)} 条职位记录"
        if names:
            evidence += f"，例如{'、'.join(names[:3])}"
        insights.append({"feature": "岗位样本", "evidence": evidence + "。",
                         "interpretation": "职位记录是本次样本，不代表全部岗位或最终录用人数。"})
    for key, label in (("education_dist", "学历要求"), ("seniority_dist", "工作年限")):
        rows = core.get(key) or []
        if rows:
            conc = _concentration(rows, label, "记录数", 1)
            if conc:
                insights.append({
                    "feature": f"{label}样本",
                    "evidence": f"本次累计有{label}信息的记录共 {int(conc['total'])} 条，其中“{conc['top']}”占约 {conc['top_share']:.0f}%。",
                    "interpretation": "仅统计本次累计有该字段的样本，不代表企业全部岗位要求。",
                })
    # 渠道只返回名单，不具备各渠道岗位量。
    source_dist = core.get("source_dist") or []
    if source_dist:
        names = [str(item) for item in source_dist if isinstance(item, str)]
        if names:
            insights.append({
                "feature": "招聘渠道",
                "evidence": f"画像返回 {len(names)} 个渠道，包括{'、'.join(names[:3])}。",
                "interpretation": "渠道列表未提供各渠道真实岗位数，不能据此衡量触达能力或排序。",
            })
    # 城市分布集中度
    city_dist = core.get("city_dist") or []
    if city_dist:
        conc = _concentration(city_dist, "城市", "岗位数", 2)
        if conc:
            insights.append({
                "feature": "地域集中度",
                "evidence": f"有城市信息的 {int(conc['total'])} 条记录中，“{conc['top']}”占比约 {conc['top_share']:.0f}%，前 2 城市合计 {conc['cr']:.0f}%（CR2），覆盖 {conc['n']} 个城市。",
                "interpretation": "城市缺失记录未计入；城市集中度仅描述已知城市的招聘样本分布，不能直接等同于企业业务地域重心。",
            })
    consistency = core.get("consistency_check") or {}
    if consistency:
        insights.append({
            "feature": "招聘数量口径区别",
            "evidence": f"趋势视图当前招聘人数 {consistency.get('趋势视图当前招聘人数')}；职位检索命中总数 {consistency.get('职位检索命中总数')}。",
            "interpretation": "人数与职位记录数不是相同口径，数值不同不代表冲突，不能将其中任一数值替代另一口径。",
        })
    if not insights:
        if metric_map.get("筛选后岗位样本数") == "0":
            insights.append({"feature": "本次累计筛选结果", "evidence": "本次累计取得的样本没有匹配筛选条件的职位。",
                             "interpretation": "其他页面可能仍有匹配记录，不能推断企业没有相关岗位。"})
        else:
            insights.append({
                "feature": "数据完整性",
                "evidence": "部分维度未返回有效数据。",
                "interpretation": "建议核对匹配关键词是否为企业全称，或检查 MCP 连接与上游数据产品覆盖范围。",
            })
    return insights


def build_abstract(subject: Mapping[str, Any], core: Mapping[str, Any], metrics: Sequence[Mapping[str, Any]],
                   plan: Optional[Mapping[str, Any]] = None, *, dry_run: bool = False) -> str:
    name = subject.get("enterprise") or subject.get("match_raw") or "目标企业"
    plan = plan or {"topics": ["full"], "warnings": []}
    topics = plan.get("topics") or ["full"]
    scope = "招聘趋势、雇主画像、招聘需求、职位薪酬与职位明细" if topics == ["full"] else "、".join(FOCUS_LABELS[t] for t in topics)
    parts = [f"本报告以“{name}”为分析对象，重点分析{scope}。"]
    if dry_run:
        parts.append("本报告使用虚构样例数据，不代表该企业的真实招聘情况。")
    if metrics:
        kv = "、".join(f"{m['label']} {m['value']}" for m in metrics[:4])
        parts.append(f"关键指标包括：{kv}。")
    if not any(_has_evidence(core.get(s.get("key") or "")) for s in core.get("sections", []) if isinstance(s, dict)):
        parts.append("所选范围内未获得有效数据，不能据此认定企业没有招聘。")
    if any(plan.get(key) for key in ("city", "job_keyword", "date_start", "date_end")):
        conditions = []
        if plan.get("city"):
            conditions.append(f"城市包含“{plan['city']}”")
        if plan.get("job_keyword"):
            conditions.append(f"职位名称包含“{plan['job_keyword']}”")
        if plan.get("date_start") or plan.get("date_end"):
            conditions.append(f"发布日期 {plan.get('date_start') or '不限起日'} 至 {plan.get('date_end') or '不限止日'}（含边界）")
        parts.append(f"筛选条件为{'、'.join(conditions)}，仅对本次累计取得的样本生效。")
        sample_metric = next((m for m in metrics if m.get("label") == "筛选后岗位样本数"), None)
        if sample_metric is not None and str(sample_metric.get("value")) == "0":
            parts.append("本次累计未匹配筛选条件，不能推断其他页面没有匹配职位。")
    parts.extend(plan.get("warnings") or [])
    return "".join(parts)


# --------------------------------------------------------------------------- #
# Dry-run sample
# --------------------------------------------------------------------------- #

def build_dry_run_payload(raw: str, keyword_type: str, question: str = "", city: str = "",
                          job_keyword: str = "", page_size: int = 50,
                          view: str = "statistics", focus: Optional[Sequence[str]] = None,
                          sample_size: Optional[int] = None, max_pages: Optional[int] = None,
                          date_start: str = "", date_end: str = "") -> Dict[str, Any]:
    """Run the same routing and filtering as live mode on clearly marked sample data."""
    try:
        sample = load_json_file(SAMPLE_PATH)
    except Exception:
        sample = {}
    sample = sample if isinstance(sample, dict) else {}
    sample_core = sample.get("core_analysis") or {}
    values = {item.get("label"): item.get("value") for item in sample.get("metrics", []) if isinstance(item, dict)}
    trend = {
        "recruitingCurrentCount": values.get("当前招聘人数"),
        "recruitingLastThreeMonthCount": values.get("近三月招聘人数"),
        "recruitingLastThreeMonthNo": values.get("近三月岗位数"),
        "recruitingAvgUpdate": values.get("平均更新频率"),
        "recruitingAvgWorkingSalary": values.get("平均薪酬"),
    }
    profile = {
        **trend,
        "benefitList": sample_core.get("benefit_tags") or [],
        "recruitingPositionKeyWords": sample_core.get("position_keywords") or [],
        "recruitingCities": [r.get("城市") for r in sample_core.get("city_dist", []) if isinstance(r, dict) and r.get("城市")],
        "recruitingSources": [r.get("渠道") for r in sample_core.get("source_dist", []) if isinstance(r, dict) and r.get("渠道")],
    }
    rows = [{"recruitingName": r.get("职位名称"), "recruitingCity": r.get("城市"),
             "recruitingSource": r.get("渠道"), "workingSalary": f"{r.get('薪酬')} 人民币" if r.get("薪酬") else None,
             "recruitingPublishedTime": r.get("发布日期"), "recruitingEducation": "本科" if index == 0 else "硕士",
             "workingSeniority": {"min": 1, "max": 3} if index == 0 else {"min": 3, "max": 5}}
            for index, r in enumerate(sample_core.get("job_records", [])) if isinstance(r, dict)]
    city, job_keyword, warnings = _question_constraints(question, raw, city, job_keyword)
    plan = _focus_plan(question, focus, view, city, job_keyword, raw)
    plan["warnings"].extend(warnings)
    _set_date_scope(plan, date_start, date_end)
    _set_page_scope(plan, page_size, sample_size, max_pages)
    plan["warnings"].append("dry-run 仅验证样例与报告结构，不进行真实分页，pagination 为空；不得用作正式采集完整性证据。")
    selected = _first_list(_filter_page({"resultList": rows}, city, job_keyword, plan["date_start"], plan["date_end"]))
    target = plan["sample_size"]
    page = {"total": len(rows), "resultList": selected[:target] if target is not None else selected}
    if target is not None and target > len(selected):
        plan["warnings"].append(f"模拟数据仅有 {len(rows)} 条，未达到目标 {plan['sample_size']} 条。")
    calls = {tool: (trend if tool == T_TREND else profile if tool == T_PROFILE else
                    page if tool in (T_SALARY, T_JOB_SEARCH) or (tool == T_DEMAND and plan["view"] == "details")
                    else profile) for tool in plan["tools"]}
    subject = build_subject(raw, resolve_enterprise_name(raw, keyword_type), keyword_type)
    return _report_from_calls(subject, calls, plan, dry_run=True)


# --------------------------------------------------------------------------- #
# Assembly
# --------------------------------------------------------------------------- #

def _assemble(subject: Mapping[str, Any], core: Mapping[str, Any], metrics: Sequence[Mapping[str, Any]], *,
              dry_run: bool, plan: Optional[Mapping[str, Any]] = None,
              products: Optional[Sequence[Mapping[str, Any]]] = None) -> Dict[str, Any]:
    plan = plan or _focus_plan("", None, "statistics", "", "")
    abstract = build_abstract(subject, core, metrics, plan, dry_run=dry_run)
    records = build_records(core)
    insights = build_insights(subject, core, metrics)
    # Quality gate: count populated core-analysis sections.
    ca = core if isinstance(core, dict) else {}
    secs = ca.get("sections", [])
    if secs:
        total_secs = len(secs)
        populated = sum(1 for s in secs if isinstance(s, dict) and _has_evidence(ca.get(s.get("key"))))
    else:
        total_secs = max(1, len([k for k in ca if k != "sections"]))
        populated = sum(1 for k in ca if k != "sections" and _has_evidence(ca.get(k)))
    quality_report = {
        "total_sections": total_secs,
        "populated_sections": populated,
        "empty_sections": total_secs - populated,
        "coverage_pct": round(populated / max(1, total_secs) * 100),
    }
    if populated == 0:
        import sys
        print("⚠️ 质量门禁警告: 所有核心分析维度均无数据", file=sys.stderr)
    topics = plan.get("topics") or ["full"]
    title_suffix = "招聘大数据报告" if topics == ["full"] else "、".join(FOCUS_LABELS[t] for t in topics) + "分析报告"
    title = f"{subject.get('enterprise') or '目标企业'} {title_suffix}"
    caliber = build_caliber(subject)
    caliber["data_scope"] = "招聘趋势概览、雇主画像、招聘需求、职位薪酬与职位明细" if topics == ["full"] else "、".join(FOCUS_LABELS[t] for t in topics)
    caliber["products"] = [p["name"] for p in products or []]
    limitations = list(plan.get("warnings") or []) + list(plan.get("collection_notes") or [])
    caliber["limit"] = "招聘数据可能滞后；分析对象为公开发布记录，不等同于去重职位数、当前在招人数或实际录用。是否已遍历源分页见采集状态。" + "".join(limitations)
    return {
        "report_type": REPORT_TYPE,
        "title": title,
        "banner": REPORT_BANNER,
        "subject": dict(subject),
        "abstract": abstract,
        "summary": abstract,
        "executive_summary": [f"{item['feature']}：{item['evidence']}{item['interpretation']}" for item in insights][:5] or [abstract[:120]],
        "metrics": list(metrics),
        "caliber": caliber,
        "core_analysis": dict(core),
        "representative_records": records,
        "insights": insights,
        "analysis_request": {"question": plan.get("question", ""), "focus": list(topics), "excluded": list(plan.get("excluded") or []),
                             "filters": {"city": plan.get("city", ""), "job_keyword": plan.get("job_keyword", ""),
                                         "date_start": plan.get("date_start", ""), "date_end": plan.get("date_end", "")},
                             "demand_view": plan.get("view"), "page_size": plan.get("page_size"),
                             "sample_size": plan.get("sample_size"), "max_pages": plan.get("max_pages"),
                             "collection_mode": plan.get("collection_mode"),
                             "call_plan": dict(plan.get("call_plan") or {}),
                             "pagination": dict(plan.get("pagination") or {}),
                             "limitations": limitations},
        "data_source": {
            "mcp_server": "recruitment-mcp-server",
            "products": list(products or []),
            "generated_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
            "dry_run": dry_run,
            "quality_report": quality_report,
            "pagination": dict(plan.get("pagination") or {}),
        },
    }


def _matches_row(row: Any, city: str, job_keyword: str, date_start: str = "", date_end: str = "") -> bool:
    if not isinstance(row, dict):
        return False
    city_term = city.casefold().removesuffix("市")
    if city_term and city_term not in _text(row.get("recruitingCity")).casefold():
        return False
    if job_keyword and job_keyword.casefold() not in _text(row.get("recruitingName")).casefold():
        return False
    if date_start or date_end:
        published = _published_date(row.get("recruitingPublishedTime"))
        if published is None:
            return False
        value = published.isoformat()
        if date_start and value < date_start or date_end and value > date_end:
            return False
    return True


def _filter_page(payload: Any, city: str, job_keyword: str, date_start: str = "", date_end: str = "") -> Any:
    """Filter only returned page rows; never relabel the upstream enterprise total."""
    if not (city or job_keyword or date_start or date_end) or _is_api_error(payload) or _is_empty_response(payload):
        return payload
    def matches(row: Any) -> bool:
        return _matches_row(row, city, job_keyword, date_start, date_end)

    if isinstance(payload, list):
        return [row for row in payload if matches(row)]
    if isinstance(payload, dict):
        result = dict(payload)
        result.pop("total", None)
        for key in ("resultList", "list", "items", "data"):
            if isinstance(result.get(key), list):
                result[key] = [row for row in result[key] if matches(row)]
            elif key == "data" and isinstance(result.get(key), dict):
                result[key] = _filter_page(result[key], city, job_keyword, date_start, date_end)
        return result
    return payload



def _collect_pages(tool: str, args: Mapping[str, Any], plan: Dict[str, Any]) -> Any:
    """Use total-driven collection without confusing filtered samples with source counts."""
    date_unknown = 0
    dates: List[str] = []
    matched_dates: List[str] = []

    def matches(row: Any) -> bool:
        nonlocal date_unknown
        published = _published_date(row.get("recruitingPublishedTime")) if isinstance(row, dict) else None
        if published is None:
            date_unknown += 1
        else:
            dates.append(published.isoformat())
        matched = _matches_row(row, plan["city"], plan["job_keyword"], plan["date_start"], plan["date_end"])
        if matched and published is not None:
            matched_dates.append(published.isoformat())
        return matched

    result = collect_detail_pages(
        _safe_call, tool, dict(args), get_rows=_first_list, get_total=_safe_total,
        is_error=_is_api_error, max_pages=plan["max_pages"],
        sample_size=plan["sample_size"], matches=matches,
    )
    info = result["_pagination"]
    info.update(
        date_unknown_count=date_unknown,
        date_range={"start": min(dates) if dates else None, "end": max(dates) if dates else None},
        matched_date_range={"start": min(matched_dates) if matched_dates else None,
                            "end": max(matched_dates) if matched_dates else None},
    )
    plan["pagination"][TOOL_LABELS[tool]] = info
    pages, fetched, matched = info["pages_fetched"], info["rows_fetched"], info["sample_count"]
    total, reason, target = info["upstream_total"], info["stop_reason"], plan["sample_size"]
    prefix = f"{TOOL_LABELS[tool]}读取 {pages} 页、上游返回 {fetched} 条，取得 {matched} 条样本"
    if total is not None:
        prefix += (f"；上游企业未筛选记录总数 {total}，按单页 {info['page_size']} 条预计 {info['total_pages']} 页"
                   f"；尚未扫描 {info['remaining_rows']} 条，尚未获取 {info['unfetched_rows']} 条"
                   f"（按请求页大小预计还需 {info['remaining_pages']} 页）")
    if matched_dates:
        prefix += f"；分析记录发布日期跨度 {min(matched_dates)} 至 {max(matched_dates)}"
    plan.setdefault("collection_notes", []).append(prefix + "。")
    if not info["source_exhausted"]:
        plan["warnings"].append(f"{TOOL_LABELS[tool]}尚未完成源分页遍历，数据不完整，不能据此推断企业全部岗位或完整时间窗口分布。")
    if date_unknown and (plan["date_start"] or plan["date_end"]):
        plan["warnings"].append(f"已扫描记录中 {date_unknown} 条发布日期缺失或无法解析，已排除出请求日期窗口；即使源分页遍历结束也不代表该窗口完整无缺。")
    if reason == "error":
        plan["warnings"].append(f"{TOOL_LABELS[tool]}第 {info['failed_page']} 页查询失败，保留已获取的 {matched} 条样本。")
    elif reason == "max_pages":
        goal = f"目标 {target} 条" if target is not None else "按问题范围覆盖（无固定条数目标）"
        plan["warnings"].append(f"达到最多 {plan['max_pages']} 页费用护栏，{goal}，实际 {matched} 条；本次采集未完整覆盖。")
    elif reason == "repeated_page":
        previous = "上一页" if info["repeated_from_page"] == pages - 1 else f"第 {info['repeated_from_page']} 页"
        plan["warnings"].append(f"第 {pages} 页与{previous}完全相同，疑似重复页，已停止翻页；重复返回量不计入有效采集量。")
    elif reason == "total_changed":
        plan["warnings"].append(f"翻页期间上游 total 从 {total} 变为 {info['latest_total']}，本次未形成同一总量下的完整采集。")
    elif reason == "missing_total":
        plan["warnings"].append("明细接口未返回有效 total，不能计算总页数或宣称采集完整，已停止继续调用。")
    elif reason == "count_mismatch":
        plan["warnings"].append(f"有效返回量 {info['rows_accepted']} 超过上游 total={total}，数量不一致，不标记为完整。")
    elif reason in ("total_exhausted", "empty_page") and target is not None and matched < target:
        plan["warnings"].append(f"数据源共返回 {fetched} 条，本次样本 {matched} 条，未达到目标 {target} 条；停止原因：{reason}。")
    return result

def _has_list_response(payload: Any) -> bool:
    if _is_api_error(payload):
        return False
    if isinstance(payload, list):
        return True
    if isinstance(payload, dict):
        return any(isinstance(payload.get(k), list) for k in ("resultList", "list", "items", "data")) or (
            isinstance(payload.get("data"), dict) and _has_list_response(payload["data"]))
    return False


def _select_core(core: Mapping[str, Any], plan: Mapping[str, Any]) -> Dict[str, Any]:
    topics = plan["topics"]
    if topics == ["full"]:
        keys = [s["key"] for s in core.get("sections", []) if s.get("key") != "demand_details" or plan["view"] == "details"]
    else:
        keys = []
        for topic in topics:
            relevant = {
                "trend": ["trend_overview"],
                "profile": ["employer_profile", "benefit_tags", "compensation_tags", "hiring_requirements",
                            "employer_descriptions", "unclassified_tags", "position_keywords", "source_dist"],
                "demand": ["demand_details", "title_dist"] if plan["view"] == "details" else ["demand_stats", "position_keywords"],
                "salary": ["salary_dist", "salary_records"],
                "jobs": ["job_records"],
                "city": (["city_dist", "salary_by_city"] if "salary" in topics else
                         ["city_dist"] if "jobs" in plan.get("excluded", []) else ["city_dist", "job_records"]),
            }[topic]
            for key in relevant:
                if key not in keys:
                    keys.append(key)
        if "trend" in topics and "jobs" in topics and not (plan["city"] or plan["job_keyword"]):
            keys.append("consistency_check")
        if "jobs" in topics or ("demand" in topics and plan["view"] == "details"):
            question = plan.get("question", "")
            if re.search(r"学历|教育要求|本科|硕士|博士|研究生|大专|专科", question):
                keys.append("education_dist")
            if re.search(r"经验|年限|应届", question):
                keys.append("seniority_dist")
    specs = {s["key"]: s for s in core.get("sections", [])}
    selected: Dict[str, Any] = {"sections": [dict(specs[k]) for k in keys if k in specs], **{k: core.get(k) for k in keys}}
    if "benefit_tags" in keys:
        for key in ("benefit_source_labels", "benefit_label_evidence", "benefit_label_quality"):
            selected[key] = core.get(key)
    if "salary" not in topics and topics != ["full"] and isinstance(selected.get("trend_overview"), list):
        selected["trend_overview"] = [row for row in selected["trend_overview"] if row.get("指标") != "平均薪酬"]
    if "salary" in plan.get("excluded", []):
        selected["sections"] = [s for s in selected["sections"] if s["key"] not in ("salary_dist", "salary_records", "salary_by_city")]
        for key in ("salary_dist", "salary_records", "salary_by_city"):
            selected.pop(key, None)
        selected.pop("compensation_tags", None)
        selected["sections"] = [s for s in selected["sections"] if s["key"] != "compensation_tags"]
        for key in ("employer_profile", "demand_stats"):
            if isinstance(selected.get(key), dict):
                selected[key] = {k: v for k, v in selected[key].items() if "薪酬" not in k and "薪资" not in k}
        for key in ("job_records", "demand_details"):
            if isinstance(selected.get(key), list):
                selected[key] = [{k: v for k, v in row.items() if k != "薪酬"} for row in selected[key]]
        for spec in selected["sections"]:
            if spec.get("key") in ("job_records", "demand_details"):
                spec["columns"] = [column for column in spec.get("columns", []) if column[0] != "薪酬"]
    return selected


def _report_from_calls(subject: Mapping[str, Any], calls: Mapping[str, Any], plan: Mapping[str, Any], *, dry_run: bool) -> Dict[str, Any]:
    date_start, date_end = plan.get("date_start", ""), plan.get("date_end", "")
    has_filters = bool(plan["city"] or plan["job_keyword"] or date_start or date_end)
    filtered = {tool: _filter_page(payload, plan["city"], plan["job_keyword"], date_start, date_end)
                if tool in (T_JOB_SEARCH, T_SALARY) or (tool == T_DEMAND and plan["view"] == "details") else payload
                for tool, payload in calls.items()}
    core = build_core_analysis(filtered.get(T_TREND), filtered.get(T_PROFILE), filtered.get(T_DEMAND),
                               filtered.get(T_SALARY), filtered.get(T_JOB_SEARCH), plan["view"])
    core = _select_core(core, plan)
    overall: Mapping[str, Any] = next((calls[t] for t in (T_TREND, T_PROFILE, T_DEMAND)
                    if t in calls and (t != T_DEMAND or plan["view"] == "statistics")
                    and isinstance(calls[t], dict) and not _is_api_error(calls[t])), {})
    job_total = _safe_total(calls.get(T_JOB_SEARCH)) if not has_filters else None
    metrics = build_metrics(overall, job_total)
    if "salary" in plan.get("excluded", []) or (plan["topics"] != ["full"] and "salary" not in plan["topics"] and "profile" not in plan["topics"] and "demand" not in plan["topics"]):
        metrics = [m for m in metrics if m["label"] != "平均薪酬"]
    if has_filters:
        for metric in metrics:
            metric["hint"] += "；企业整体口径，未按本报告明细筛选条件过滤"
    for tool, key in ((T_JOB_SEARCH, "job_records"), (T_DEMAND, "demand_details"), (T_SALARY, "salary_records")):
        if key in core and tool in filtered and _has_list_response(calls[tool]) and _first_list(calls[tool]):
            label = "筛选后岗位样本数" if has_filters else "本次岗位样本数"
            prefix = "跨页累计" if any(info["pages_fetched"] > 1 for info in plan.get("pagination", {}).values()) else "本次累计"
            metrics.append({"label": label, "value": str(len(core.get(key) or [])), "hint": f"{prefix}取得并纳入分析的岗位记录数，不是企业岗位总数或实际在招人数"})
            break
    if core.get("benefit_source_labels"):
        metrics.append({"label": "福利与工作安排项", "value": str(len(core.get("benefit_tags") or [])),
                        "hint": "来源标签规范整理后的去重项数，不含薪酬、任职条件、宣传和待核验项；不代表全员福利数"})
    _derive_core_metrics(metrics, core)
    products = []
    if any(t in calls for t in (T_TREND, T_PROFILE)) or (T_DEMAND in calls and plan["view"] == "statistics"):
        products.append(PRODUCT_STATISTICS)
    if any(t in calls for t in (T_SALARY, T_JOB_SEARCH)) or (T_DEMAND in calls and plan["view"] == "details"):
        products.append(PRODUCT_DETAILS)
    report = _assemble(subject, core, metrics, dry_run=dry_run, plan=plan, products=products)
    if core.get("benefit_label_quality"):
        report["data_source"]["content_quality"] = dict(core["benefit_label_quality"])
    if not dry_run:
        _attach_call_status(report, {TOOL_LABELS[t]: p for t, p in calls.items()})
        failed = report["data_source"]["failed_products"]
        for label, info in plan.get("pagination", {}).items():
            if info["stop_reason"] == "error" and label not in failed:
                failed.append(label)
        empty = report["data_source"]["empty_products"]
        disclosure = (f"以下所选范围查询失败：{'、'.join(failed)}。" if failed else "")
        disclosure += (f"以下所选范围未返回数据：{'、'.join(empty)}；空结果不代表该事项不存在。" if empty else "")
        if disclosure:
            report["abstract"] += disclosure
            report["summary"] += disclosure
            report["caliber"]["limit"] += disclosure
    return report


@paid_call_scope
def build_payload(raw: str, keyword_type: str, view: str, page_size: int, question: str = "",
                  city: str = "", job_keyword: str = "", focus: Optional[Sequence[str]] = None,
                  sample_size: Optional[int] = None, max_pages: Optional[int] = None,
                  date_start: str = "", date_end: str = "") -> Dict[str, Any]:
    city, job_keyword, warnings = _question_constraints(question, raw, city, job_keyword)
    plan = _focus_plan(question, focus, view, city, job_keyword, raw)
    plan["warnings"].extend(warnings)
    _set_date_scope(plan, date_start, date_end)
    _set_page_scope(plan, page_size, sample_size, max_pages)
    detail_tools = [tool for tool in plan["tools"] if tool in (T_SALARY, T_JOB_SEARCH)
                    or (tool == T_DEMAND and plan["view"] == "details")]
    statistics_tools = [tool for tool in plan["tools"] if tool not in detail_tools]
    statistics_source = (T_PROFILE if T_PROFILE in statistics_tools else
                         T_DEMAND if T_DEMAND in statistics_tools else T_TREND)
    source_for = {tool: detail_tools[0] if tool in detail_tools else statistics_source
                  for tool in plan["tools"]}
    source_tools = list(dict.fromkeys(source_for.values()))
    reused = {TOOL_LABELS[tool]: TOOL_LABELS[source] for tool, source in source_for.items() if tool != source}
    maximum_calls = sum(plan["max_pages"] if tool in detail_tools else 1 for tool in source_tools)
    plan["call_plan"] = {
        "required_dimensions": [TOOL_LABELS[tool] for tool in plan["tools"]],
        "source_tools": source_tools, "detail_page_budget": plan["max_pages"], "budget_basis": plan["budget_basis"],
        "maximum_business_requests": maximum_calls, "reused_dimensions": reused,
    }
    notes = plan.setdefault("collection_notes", [])
    notes.append(f"先规划后查询：本次仅查询所需的 {len(source_tools)} 组数据，最多 {maximum_calls} 次业务请求（每页扣费）；统计与明细不为重复章节重复购买。")
    if reused:
        notes.append("；".join(f"{label}复用{source}的同产品、同主体结果" for label, source in reused.items()) + "，不新增相同数据调用，也不叠加为独立记录。")
    resolved = resolve_enterprise_name(raw, keyword_type)
    if resolved.get("requires_confirmation"):
        subject = build_subject(raw, resolved, keyword_type)
        return _apply_resolution_limit(_assemble(subject, {"sections": []}, [], dry_run=False, plan=plan), resolved)
    enterprise = resolved["enterprise"]
    mk_args: Dict[str, Any] = {"matchKeyword": enterprise, "keywordType": keyword_type}
    search_args: Dict[str, Any] = {**mk_args, "pageIndex": 1, "pageSize": page_size}

    sources: Dict[str, Any] = {}
    calls = {}
    for logical_tool in plan["tools"]:
        tool = source_for[logical_tool]
        if tool not in sources:
            if tool == T_DEMAND:
                args = {**mk_args, "view": plan["view"]}
                args.update({"pageIndex": 1, "pageSize": page_size} if plan["view"] == "details" else {"listLimit": 50})
            elif tool in (T_SALARY, T_JOB_SEARCH):
                args = search_args
            elif tool == T_PROFILE:
                args = {**mk_args, "listLimit": 50}
            else:
                args = mk_args
            sources[tool] = _collect_pages(tool, args, plan) if tool in detail_tools else _safe_call(tool, args)
        calls[logical_tool] = sources[tool]
    subject = build_subject(raw, resolved, keyword_type)
    return _report_from_calls(subject, calls, plan, dry_run=False)


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def main() -> None:
    parser = argparse.ArgumentParser(description="Compose a recruitment big-data report via the recruitment MCP.")
    parser.add_argument("--enterprise", required=True, help="企业全称（招聘 MCP 无模糊查询，建议直接提供企业全称）")
    parser.add_argument("--keyword-type", default="name", choices=["name", "nameId", "regNumber", "socialCreditCode"], help="主体类型")
    parser.add_argument("--view", default="statistics", choices=["details", "statistics"], help="招聘需求分析视图：details=岗位级需求；statistics=企业汇总需求")
    parser.add_argument("--question", default="", help="用户原始问题：按问题选择报告重点和数据范围")
    parser.add_argument("--focus", action="append", choices=["full", *FOCUS_LABELS], help="明确指定重点，可重复；覆盖问题的关键词推断")
    parser.add_argument("--city", default="", help="对已获取的分页职位样本按城市做本地包含筛选")
    parser.add_argument("--job-keyword", default="", help="对已获取的分页职位样本按职位名称做本地包含筛选")
    parser.add_argument("--page-size", type=int, help="每页明细数量（1–50）")
    parser.add_argument("--sample-size", type=int, help="明确需要的匹配记录数；默认从前N条推断，否则持续翻页尽量覆盖，不以每页数量为目标")
    parser.add_argument("--max-pages", type=int, help="规划的付费页数上限；默认只取1页，无本地筛选且明确N条时自动安排ceil(N/pageSize)页")
    parser.add_argument("--date-start", default="", help="本地按发布日期筛选的起日 YYYY-MM-DD（含）；显式日期覆盖问题推断")
    parser.add_argument("--date-end", default="", help="本地按发布日期筛选的止日 YYYY-MM-DD（含）；上游没有日期过滤/排序保证")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="使用样例数据（默认），不调用真实 MCP")
    mode.add_argument("--live", action="store_true", help="明确授权真实 MCP 数据查询（可能付费）")
    parser.add_argument("--output", help="输出 JSON 路径；省略则打印到 stdout")
    parser.add_argument("--report-output", help="同时输出 HTML 报告（.html）与 Markdown 报告（.md）")
    parser.add_argument("--pdf-output", help="额外输出 PDF 报告（.pdf）；需要 Playwright + Chromium")
    args = parser.parse_args()

    page_size = args.page_size
    if page_size is None:
        requested = _requested_page_size(args.question)
        page_size = min(requested, 50) if requested is not None else 50
    if not 1 <= page_size <= 50:
        parser.error("--page-size 必须在 1 到 50 之间")

    if (args.sample_size is not None and args.sample_size < 1) or (args.max_pages is not None and args.max_pages < 1):
        parser.error("--sample-size 和 --max-pages 必须为正整数")

    dry_run = not args.live
    try:
        if dry_run:
            payload = build_dry_run_payload(args.enterprise, args.keyword_type, args.question, args.city,
                                            args.job_keyword, page_size, args.view, args.focus, args.sample_size, args.max_pages,
                                            args.date_start, args.date_end)
        else:
            payload = build_payload(args.enterprise, args.keyword_type, args.view, page_size,
                                    args.question, args.city, args.job_keyword, args.focus, args.sample_size, args.max_pages,
                                    args.date_start, args.date_end)
    except ValueError as exc:
        parser.error(str(exc))

    if args.output:
        out = pathlib.Path(args.output).expanduser()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json_dumps(payload, pretty=True), encoding="utf-8")
        print_json({"ok": True, "json": str(out), "dry_run": dry_run})
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
        print_json({"ok": True, "html": str(html_path), "markdown": str(md_path), "pdf": str(pdf_path) if args.pdf_output else None, "dry_run": dry_run})


if __name__ == "__main__":
    main()
