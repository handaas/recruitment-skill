#!/usr/bin/env python3
"""Shared helpers for the trademark-skill.

These helpers purposefully mirror the conventions of the reference
industry-chain-processing skill: standard-library only, JSON output with
ensure_ascii=False, secret redaction, and no third-party deps in this file.
"""
from __future__ import annotations

import json
import os
import pathlib
import sys
import urllib.parse
from typing import Any, Dict, Optional

SKILL_DIR = pathlib.Path(__file__).resolve().parents[1]
EXAMPLE_CONFIG = SKILL_DIR / "assets" / "config.example.json"

# Domain constants — change per skill when copying this template.
DOMAIN = "recruitment"
DOMAIN_UPPER = "RECRUITMENT"
MCP_SERVER_DIR = "recruitment-mcp-server"
MCP_SERVER_NAME = "招聘大数据"
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
