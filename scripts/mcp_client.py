#!/usr/bin/env python3
"""MCP client for the recruitment-report skill.

Connects to the upstream HandaaS MCP server in two ways:

1. **Remote MCP (preferred)** — set ``RECRUITMENT_MCP_URL`` (or the generic
   ``HANDAAS_MCP_URL``) to a streamable-http endpoint. The official HandaaS
   endpoint uses a runtime ``token`` query parameter; other hosts use Bearer auth.
2. **Local MCP (fallback)** — when no URL is configured, the client boots the
   local ``handaas-mcp-server/recruitment-mcp-server/server/mcp_server.py`` over
   stdio using the MCP SDK. The local server reads its own ``.env`` for
   credentials; this client never handles secrets.

Usage::

    python mcp_client.py ping
    python mcp_client.py list-tools
    python mcp_client.py call-tool --tool recruitment_employer_profile \
        --arguments-json '{"matchKeyword": "某企业全称", "keywordType": "name"}'

This file prints only redacted config in errors and never prints
tokens/signatures/credentials.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import pathlib
import urllib.parse
from contextlib import contextmanager
from typing import Any, Dict, Optional

from common import (
    DOMAIN_UPPER,
    MCP_SERVER_DIR,
    ConfigError,
    env,
    is_placeholder,
    load_config,
    print_json,
    redact,
)


# --------------------------------------------------------------------------- #
# Config resolution
# --------------------------------------------------------------------------- #

def resolve_mcp_url() -> Optional[str]:
    url = env(f"{DOMAIN_UPPER}_MCP_URL", "HANDAAS_MCP_URL")
    if not url or is_placeholder(url):
        return None
    return url


def resolve_mcp_token() -> Optional[str]:
    token = env(f"{DOMAIN_UPPER}_MCP_TOKEN")
    if not token or is_placeholder(token):
        return None
    return token


def resolve_local_server_path() -> Optional[pathlib.Path]:
    """Locate the upstream MCP server.py for stdio bootstrap."""
    config = load_config(allow_example=False)
    explicit = (config.get("mcp_server_root") or "").strip() if isinstance(config, dict) else ""
    candidates = []
    if explicit:
        candidates.append(pathlib.Path(explicit).expanduser())
    env_root = env("HANDAAS_MCP_SERVER_ROOT")
    if env_root:
        candidates.append(pathlib.Path(env_root).expanduser() / MCP_SERVER_DIR / "server" / "mcp_server.py")
    # Common sibling layout: <project>/handaas-mcp-server/<server>/server/mcp_server.py
    here = pathlib.Path(__file__).resolve()
    for parent in [here.parents[2], pathlib.Path.cwd(), pathlib.Path.cwd().parent, pathlib.Path.home() / "Project"]:
        candidates.append(parent / "handaas-mcp-server" / MCP_SERVER_DIR / "server" / "mcp_server.py")
    for candidate in candidates:
        if candidate and candidate.exists():
            return candidate.resolve()
    return None


def get_connection_config() -> Dict[str, Any]:
    """Return a descriptor of how we will connect (remote preferred)."""
    url = resolve_mcp_url()
    if url:
        token = resolve_mcp_token() or ""
        _remote_auth_options(url, token)
        return {"mode": "remote", "url": url, "token": token}
    local_path = resolve_local_server_path()
    if local_path:
        return {"mode": "local", "server_path": str(local_path)}
    return {}


# --------------------------------------------------------------------------- #
# Result extraction
# --------------------------------------------------------------------------- #

def _plain(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json", by_alias=True)
    if isinstance(value, dict):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_plain(item) for item in value]
    return value


def _extract_tool_result(value: Any) -> Any:
    plain = _plain(value)
    if isinstance(plain, dict):
        # MCP CallToolResult failure state takes precedence over any content.
        if plain.get("isError") is True or plain.get("is_error") is True:
            return {"_error": "MCP tool call failed"}
        structured = plain.get("structuredContent") or plain.get("structured_content")
        if structured is not None:
            if isinstance(structured, dict) and set(structured.keys()) == {"result"}:
                return structured["result"]
            return structured
        content = plain.get("content")
        if isinstance(content, list) and content:
            texts = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    texts.append(str(item.get("text") or ""))
            text = "\n".join(texts).strip()
            if text:
                try:
                    return json.loads(text)
                except json.JSONDecodeError:
                    return {"text": text}
    return plain


def _tools_to_list(payload: Any) -> list:
    if isinstance(payload, dict):
        if isinstance(payload.get("tools"), list):
            return payload["tools"]
    if isinstance(payload, list):
        return payload
    return []


def tool_count(payload: Any) -> int:
    return len(_tools_to_list(payload))


# --------------------------------------------------------------------------- #
# Remote MCP (streamable-http)
# --------------------------------------------------------------------------- #

def _remote_auth_options(url: str, token: str) -> tuple[Dict[str, str], Dict[str, str]]:
    try:
        parsed = urllib.parse.urlsplit(url)
        query = dict(urllib.parse.parse_qsl(parsed.query, keep_blank_values=True))
    except ValueError:
        raise ConfigError("Remote MCP URL 格式无效") from None
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ConfigError("Remote MCP 必须使用完整的 HTTP / HTTPS 地址")
    official = parsed.hostname == "mcp.handaas.com"
    if official and parsed.scheme != "https":
        raise ConfigError("旷湖平台 MCP 必须使用 HTTPS")
    if "token" in query:
        if not query["token"]:
            raise ConfigError("请移除 MCP URL 中的空 token 参数，并通过环境变量提供完整 Token")
        return {}, {}
    if official:
        if not token:
            raise ConfigError("旷湖平台 MCP 缺少 Token；请设置 RECRUITMENT_MCP_TOKEN")
        return {}, {"token": token}
    return ({"Authorization": f"Bearer {token}"} if token else {}), {}


class _CredentialLogFilter(logging.Filter):
    def __init__(self, url: str, token: str):
        super().__init__()
        values = [token]
        try:
            values.extend(value for key, value in urllib.parse.parse_qsl(
                urllib.parse.urlsplit(url).query
            ) if key.lower() in {"token", "signature", "secret", "secret_id", "secret_key"})
        except ValueError:
            pass
        self.values = sorted({
            variant for value in values if value
            for variant in (value, urllib.parse.quote(value, safe=""), urllib.parse.quote_plus(value))
        }, key=len, reverse=True)

    def redact_text(self, text: str) -> str:
        for value in self.values:
            text = text.replace(value, "***REDACTED***")
        return text

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = self.redact_text(record.getMessage())
        record.args = ()
        if record.exc_info:
            record.exc_text = self.redact_text(logging.Formatter().formatException(record.exc_info))
            record.exc_info = None
        elif record.exc_text:
            record.exc_text = self.redact_text(record.exc_text)
        if record.stack_info:
            record.stack_info = self.redact_text(record.stack_info)
        return True


@contextmanager
def _private_remote(url: str, token: str):
    privacy = _CredentialLogFilter(url, token)
    handlers = set(logging.getLogger().handlers)
    for logger in logging.Logger.manager.loggerDict.values():
        if isinstance(logger, logging.Logger):
            handlers.update(logger.handlers)
    if logging.lastResort is not None:
        handlers.add(logging.lastResort)
    for handler in handlers:
        handler.addFilter(privacy)
    try:
        yield
    except ConfigError:
        raise
    except Exception as exc:
        statuses = set()

        def collect_statuses(error):
            status = getattr(getattr(error, "response", None), "status_code", None)
            if isinstance(status, int):
                statuses.add(status)
            for child in getattr(error, "exceptions", ()):
                collect_statuses(child)

        collect_statuses(exc)
        status_text = "；HTTP " + "/".join(map(str, sorted(statuses))) if statuses else ""
        raise ConfigError(
            f"Remote MCP 请求失败（{type(exc).__name__}{status_text}）；请核对地址、Token 授权和网络状态"
        ) from None
    finally:
        for handler in handlers:
            handler.removeFilter(privacy)


async def _remote_call_tool(url: str, token: str, tool: str, arguments: Dict[str, Any], timeout: int) -> Any:
    try:
        import httpx
        from mcp import ClientSession
        from mcp.client.streamable_http import streamable_http_client
    except Exception as exc:  # pragma: no cover
        raise ConfigError("调用 Remote MCP 需要 Python 包 mcp 和 httpx。请运行：pip install 'mcp>=1.6.0' httpx") from exc

    with _private_remote(url, token):
        headers, params = _remote_auth_options(url, token)
        async with httpx.AsyncClient(headers=headers, params=params, timeout=httpx.Timeout(timeout, read=max(timeout, 300)), follow_redirects=True) as http_client:
            async with streamable_http_client(url=url, http_client=http_client) as streams:
                read_stream, write_stream, *_ = streams
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    result = await session.call_tool(tool, arguments)
                    return _extract_tool_result(result)


async def _remote_list_tools(url: str, token: str, timeout: int) -> Any:
    try:
        import httpx
        from mcp import ClientSession
        from mcp.client.streamable_http import streamable_http_client
    except Exception as exc:  # pragma: no cover
        raise ConfigError("列出 Remote MCP tools 需要 Python 包 mcp 和 httpx。请运行：pip install 'mcp>=1.6.0' httpx") from exc

    with _private_remote(url, token):
        headers, params = _remote_auth_options(url, token)
        async with httpx.AsyncClient(headers=headers, params=params, timeout=httpx.Timeout(timeout, read=max(timeout, 300)), follow_redirects=True) as http_client:
            async with streamable_http_client(url=url, http_client=http_client) as streams:
                read_stream, write_stream, *_ = streams
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    result = await session.list_tools()
                    return _plain(result)


# --------------------------------------------------------------------------- #
# Local MCP (stdio)
# --------------------------------------------------------------------------- #

async def _local_call_tool(server_path: str, tool: str, arguments: Dict[str, Any], timeout: int) -> Any:
    try:
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
    except Exception as exc:  # pragma: no cover
        raise ConfigError("调用本地 MCP 需要 Python 包 mcp。请运行：pip install 'mcp>=1.6.0'") from exc

    server_cwd = str(pathlib.Path(server_path).resolve().parents[1])
    wrapper = str(pathlib.Path(__file__).resolve().parents[2] / "assets" / "mcp_server_wrapper.py")
    params = StdioServerParameters(command=sys_exec(), args=[wrapper, str(server_path)], env=None, cwd=server_cwd)
    async with stdio_client(params) as streams:
        read_stream, write_stream, *_ = streams
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            result = await session.call_tool(tool, arguments)
            return _extract_tool_result(result)


async def _local_list_tools(server_path: str, timeout: int) -> Any:
    try:
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
    except Exception as exc:  # pragma: no cover
        raise ConfigError("列出本地 MCP tools 需要 Python 包 mcp。请运行：pip install 'mcp>=1.6.0'") from exc

    server_cwd = str(pathlib.Path(server_path).resolve().parents[1])
    wrapper = str(pathlib.Path(__file__).resolve().parents[2] / "assets" / "mcp_server_wrapper.py")
    params = StdioServerParameters(command=sys_exec(), args=[wrapper, str(server_path)], env=None, cwd=server_cwd)
    async with stdio_client(params) as streams:
        read_stream, write_stream, *_ = streams
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            result = await session.list_tools()
            return _plain(result)


def sys_exec() -> str:
    return os.environ.get("HANDAAS_MCP_PYTHON") or "python3"


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #

def _require_connection() -> Dict[str, Any]:
    conn = get_connection_config()
    if not conn:
        raise ConfigError(
            "未配置 MCP 连接。请设置 RECRUITMENT_MCP_URL="
            "https://mcp.handaas.com/recruiting/recruiting_bigdata 与 RECRUITMENT_MCP_TOKEN，"
            "或设置 HANDAAS_MCP_SERVER_ROOT 使用本地 stdio 连接。"
        )
    return conn


def list_tools(*, timeout: int = 60) -> Any:
    conn = _require_connection()
    if conn["mode"] == "remote":
        return asyncio.run(_remote_list_tools(conn["url"], conn.get("token", ""), timeout))
    return asyncio.run(_local_list_tools(conn["server_path"], timeout))


def call_tool(tool: str, arguments: Dict[str, Any], *, timeout: int = 60) -> Any:
    conn = _require_connection()
    if conn["mode"] == "remote":
        return asyncio.run(_remote_call_tool(conn["url"], conn.get("token", ""), tool, arguments, timeout))
    return asyncio.run(_local_call_tool(conn["server_path"], tool, arguments, timeout))


def tool_names() -> list:
    payload = list_tools()
    out = []
    for item in _tools_to_list(payload):
        if isinstance(item, dict) and item.get("name"):
            out.append(str(item["name"]))
    return out


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def main() -> None:
    parser = argparse.ArgumentParser(description=f"Call the {MCP_SERVER_DIR} MCP service.")
    parser.add_argument("command", choices=["ping", "list-tools", "call-tool"])
    parser.add_argument("--tool", help="Tool name for call-tool.")
    parser.add_argument("--arguments-json", default="{}", help="Tool arguments JSON for call-tool.")
    parser.add_argument("--timeout", type=int, default=60)
    args = parser.parse_args()

    try:
        conn = _require_connection()
        if args.command == "ping":
            tools = list_tools(timeout=args.timeout)
            print_json({"ok": True, "tool_count": tool_count(tools), "mode": conn["mode"], "mcp": redact(conn)})
            return
        if args.command == "list-tools":
            print_json(list_tools(timeout=args.timeout))
            return
        if not args.tool:
            raise ConfigError("call-tool 需要 --tool")
        arguments = json.loads(args.arguments_json or "{}")
        if not isinstance(arguments, dict):
            raise ConfigError("--arguments-json 必须是 JSON object")
        print_json(call_tool(args.tool, arguments, timeout=args.timeout))
    except Exception as exc:
        print_json({"ok": False, "error": str(exc)})
        raise SystemExit(1)


if __name__ == "__main__":
    main()
