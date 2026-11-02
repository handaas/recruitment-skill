#!/usr/bin/env python3
"""Shared helpers for the trademark-skill.

These helpers purposefully mirror the conventions of the reference
industry-chain-processing skill: standard-library only, JSON output with
ensure_ascii=False, secret redaction, and no third-party deps in this file.
"""
from __future__ import annotations

import copy
import functools
import hashlib
import json
import os
import pathlib
import sys
import urllib.parse
from contextvars import ContextVar
from typing import Any, Callable, Dict, List, Optional

SKILL_DIR = pathlib.Path(__file__).resolve().parents[1]
EXAMPLE_CONFIG = SKILL_DIR / "assets" / "config.example.json"

# Domain constants — change per skill when copying this template.
DOMAIN = "recruitment"
DOMAIN_UPPER = "RECRUITMENT"
MCP_SERVER_DIR = "recruitment-mcp-server"
MCP_SERVER_NAME = "企业用人需求洞察"
REPORT_BANNER = "招聘大数据报告"
REPORT_TYPE = "recruitment_analysis"

SECRET_KEYWORDS = ("secret", "signature", "token", "api_key", "apikey", "password")


class ConfigError(RuntimeError):
    pass


class ApiError(RuntimeError):
    pass


class QualityGateError(RuntimeError):
    """Raised when quality gate check fails."""
    pass


def json_dumps(value: Any, *, pretty: bool = False) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        indent=2 if pretty else None,
        separators=None if pretty else (",", ":"),
    )


def print_json(value: Any) -> None:
    print(json_dumps(value, pretty=True))


def die(message: str, code: int = 1) -> None:
    print(message, file=sys.stderr)
    raise SystemExit(code)


def load_json_file(path: pathlib.Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConfigError(f"配置文件不存在：{path}") from exc
    except json.JSONDecodeError as exc:
        raise ConfigError(f"配置文件不是合法 JSON：{path}: {exc}") from exc


def env(*names: str) -> Optional[str]:
    for name in names:
        value = os.environ.get(name)
        if value and value.strip():
            return value.strip()
    return None


def is_placeholder(value: Any) -> bool:
    text = str(value or "").strip().lower()
    if not text:
        return True
    return (
        text.startswith("your_")
        or "your_" in text
        or "_for_" in text
        or "example.com" in text
        or "your token" in text
        or text in {"todo", "replace_me", "changeme", "xxx"}
    )


def redact_url(value: str) -> str:
    if not any(marker in value.lower() for marker in ("token=", "signature=", "secret_id=", "secret_key=")):
        return value
    try:
        parsed = urllib.parse.urlparse(value)
        query = []
        for key, item in urllib.parse.parse_qsl(parsed.query, keep_blank_values=True):
            if key.lower() in {"token", "signature", "secret", "secret_id", "secret_key"}:
                query.append((key, "REDACTED"))
            else:
                query.append((key, item))
        return urllib.parse.urlunparse(parsed._replace(query=urllib.parse.urlencode(query)))
    except Exception:
        return value


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        out: Dict[str, Any] = {}
        for key, item in value.items():
            lowered = str(key).lower()
            if any(token in lowered for token in SECRET_KEYWORDS):
                out[key] = "***REDACTED***"
            else:
                out[key] = redact(item)
        return out
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, str):
        return redact_url(value)
    return value


def resolve_config_path(config_path: Optional[str] = None, *, allow_example: bool = False) -> Optional[pathlib.Path]:
    candidates = [
        config_path,
        os.environ.get(f"{DOMAIN_UPPER}_CONFIG"),
        os.environ.get("HANDAAS_SKILLS_CONFIG"),
    ]
    for candidate in candidates:
        if candidate and pathlib.Path(candidate).expanduser().exists():
            return pathlib.Path(candidate).expanduser().resolve()
    if allow_example and EXAMPLE_CONFIG.exists():
        return EXAMPLE_CONFIG.resolve()
    return None


def load_config(config_path: Optional[str] = None, *, allow_example: bool = False) -> Dict[str, Any]:
    path = resolve_config_path(config_path, allow_example=allow_example)
    if path is None:
        return {}
    data = load_json_file(path)
    if not isinstance(data, dict):
        raise ConfigError("配置文件顶层必须是 JSON object")
    return data


_PAID_CALL_STATE: ContextVar[Optional[Dict[str, Any]]] = ContextVar("paid_call_state", default=None)


def paid_call_scope(function: Callable[..., Dict[str, Any]]) -> Callable[..., Dict[str, Any]]:
    """Reuse identical paid requests within one report, never across independent reports."""
    @functools.wraps(function)
    def wrapped(*args: Any, **kwargs: Any) -> Dict[str, Any]:
        if _PAID_CALL_STATE.get() is not None:
            return function(*args, **kwargs)
        state: Dict[str, Any] = {"responses": {}, "executed_requests": 0, "reused_requests": 0}
        token = _PAID_CALL_STATE.set(state)
        try:
            report = function(*args, **kwargs)
            report.setdefault("data_source", {})["call_usage"] = {
                "executed_requests": state["executed_requests"],
                "reused_requests": state["reused_requests"],
                "scope": "current_report_only",
            }
            return report
        finally:
            _PAID_CALL_STATE.reset(token)
    return wrapped


def call_tool_once(call: Callable[[str, Dict[str, Any]], Any], tool: str, arguments: Dict[str, Any]) -> Any:
    """Do not repay for the same tool and parameters; isolate reused mutable results."""
    state = _PAID_CALL_STATE.get()
    if state is None:
        return call(tool, arguments)
    key = (tool, json.dumps(arguments, sort_keys=True, ensure_ascii=False, separators=(",", ":")))
    if key in state["responses"]:
        state["reused_requests"] += 1
        return copy.deepcopy(state["responses"][key])
    state["executed_requests"] += 1
    try:
        result = call(tool, arguments)
    except Exception:
        state["responses"][key] = {"_error": "调用失败"}
        raise
    state["responses"][key] = copy.deepcopy(result)
    return result


def _pagination_total(value: Any) -> Optional[int]:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value >= 0 else None
    if isinstance(value, float):
        return int(value) if value >= 0 and value.is_integer() else None
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def collect_detail_pages(
    call: Callable[[str, Dict[str, Any]], Any],
    tool: str,
    arguments: Dict[str, Any],
    *,
    get_rows: Callable[[Any], List[Any]],
    get_total: Callable[[Any], Any],
    is_error: Callable[[Any], bool],
    max_pages: Optional[int] = 1,
    sample_size: Optional[int] = None,
    matches: Optional[Callable[[Any], bool]] = None,
    page_size: Optional[int] = None,
) -> Dict[str, Any]:
    """Calculate total-driven quantities within an explicit paid-page budget; default to one page."""
    size = page_size if page_size is not None else arguments.get("pageSize")
    if isinstance(size, bool) or not isinstance(size, int) or size < 1:
        raise ValueError("明细分页必须提供正整数 pageSize 或已确认的接口固定页大小")
    if max_pages is not None and (isinstance(max_pages, bool) or not isinstance(max_pages, int) or max_pages < 1):
        raise ValueError("max_pages 必须为正整数或 None")
    if sample_size is not None and (isinstance(sample_size, bool) or not isinstance(sample_size, int) or sample_size < 1):
        raise ValueError("sample_size 必须为正整数或 None")
    rows: List[Any] = []
    seen_pages: Dict[str, int] = {}
    first_payload: Any = None
    total = latest_total = None
    fetched = accepted = matched = pages = succeeded = 0
    reason = "max_pages"
    failed_page = repeated_from_page = None
    page_index = 1
    while max_pages is None or page_index <= max_pages:
        payload = call(tool, {**arguments, "pageIndex": page_index})
        pages += 1
        if first_payload is None:
            first_payload = payload
        if is_error(payload):
            reason, failed_page = "error", page_index
            break
        page_rows = get_rows(payload)
        fetched += len(page_rows)
        latest_total = _pagination_total(get_total(payload))
        if total is None:
            total = latest_total
        elif latest_total is not None and latest_total != total:
            reason = "total_changed"
            break
        if page_rows:
            fingerprint = hashlib.sha256(json.dumps(page_rows, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()
            if fingerprint in seen_pages:
                reason, repeated_from_page = "repeated_page", seen_pages[fingerprint]
                break
            seen_pages[fingerprint] = page_index
        accepted += len(page_rows)
        succeeded += 1
        for row in page_rows:
            rows.append(row)
            if matches is None or matches(row):
                matched += 1
            if sample_size is not None and matched >= sample_size:
                break
        if latest_total is None:
            reason = "missing_total"
            break
        if accepted > total:
            reason = "count_mismatch"
            break
        if sample_size is not None and matched >= sample_size:
            reason = "target_reached"
            break
        if accepted == total:
            reason = "total_exhausted"
            break
        if not page_rows:
            reason = "empty_page"
            break
        page_index += 1
    complete = total is not None and len(rows) == total and reason in ("total_exhausted", "target_reached")
    unfetched = max(total - accepted, 0) if total is not None else None
    info = {
        "sample_size": sample_size, "page_size": size, "max_pages": max_pages,
        "call_budget": max_pages,
        "estimated_calls": min(max(1, (total + size - 1) // size), max_pages) if total is not None and max_pages is not None else None,
        "collection_mode": "sample" if sample_size is not None else "coverage",
        "upstream_total": total, "latest_total": latest_total,
        "total_pages": (total + size - 1) // size if total is not None else None,
        "pages_fetched": pages, "pages_succeeded": succeeded,
        "rows_fetched": fetched, "rows_accepted": accepted, "rows_scanned": len(rows),
        "sample_count": matched,
        "remaining_rows": max(total - len(rows), 0) if total is not None else None,
        "unfetched_rows": unfetched,
        "remaining_pages": (unfetched + size - 1) // size if unfetched is not None else None,
        "source_exhausted": complete, "stop_reason": reason,
        "failed_page": failed_page, "repeated_from_page": repeated_from_page,
    }
    result = dict(first_payload) if isinstance(first_payload, dict) else {}
    if reason == "error" and not rows:
        result = {"_error": "明细接口调用失败"}
    result.update(resultList=rows, _pagination=info)
    if total is not None:
        result["total"] = total
    return result


def attach_pagination(report: Dict[str, Any], sources: Dict[str, Any]) -> Dict[str, Any]:
    """Expose per-interface totals and incomplete collection in every report format."""
    pagination = {label: payload["_pagination"] for label, payload in sources.items()
                  if isinstance(payload, dict) and isinstance(payload.get("_pagination"), dict)}
    if not pagination:
        return report
    report.setdefault("data_source", {})["pagination"] = pagination
    disclosures = []
    for label, info in pagination.items():
        total = info["upstream_total"]
        expected = info["total_pages"]
        disclosure = f"{label}：上游 total={total if total is not None else '未返回有效总量'}"
        if expected is not None:
            disclosure += f"，按单页 {info['page_size']} 条预计 {expected} 页"
        disclosure += f"，实际请求 {info['pages_fetched']} 页、取得 {info['rows_scanned']} 条"
        if info["remaining_rows"] is not None:
            disclosure += f"，未纳入 {info['remaining_rows']} 条"
        disclosure += f"；{'已完整采集' if info['source_exhausted'] else '采集不完整'}，停止原因 {info['stop_reason']}。"
        disclosures.append(disclosure)
    text = "".join(disclosures)
    if any(not info["source_exhausted"] for info in pagination.values()):
        for key in ("abstract", "summary"):
            report[key] = str(report.get(key) or "") + "明细含未完整采集的来源，数量与范围详见查询口径；不能据此推断总体。"
    caliber = report.setdefault("caliber", {})
    caliber["limit"] = str(caliber.get("limit") or "") + text
    return report
