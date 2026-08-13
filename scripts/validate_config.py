#!/usr/bin/env python3
"""Validate MCP connection config for the trademark-report skill (no secrets printed)."""
from __future__ import annotations

import argparse
from typing import Any, Dict, List

from common import ConfigError, is_placeholder, load_config, print_json, redact
from mcp_client import get_connection_config, resolve_local_server_path


def validate(*, allow_placeholders: bool = False) -> Dict[str, Any]:
    errors: List[str] = []
    warnings: List[str] = []
    conn = get_connection_config()
    modes: Dict[str, Any] = {"remote_mcp": {"ok": False}, "local_mcp": {"ok": False}}

    if conn.get("mode") == "remote":
        url = conn.get("url", "")
        if is_placeholder(url):
            (warnings if allow_placeholders else errors).append("Remote MCP URL 仍是占位值")
        modes["remote_mcp"] = {"ok": not errors, "config": redact(conn)}
    else:
        warnings.append("未设置 RECRUITMENT_MCP_URL / HANDAAS_MCP_URL；将尝试本地 stdio 连接。")

    local_path = resolve_local_server_path()
    if local_path:
        modes["local_mcp"] = {"ok": True, "server_path": str(local_path)}
    else:
        modes["local_mcp"] = {"ok": False, "error": "未找到本地 MCP server（handaas-mcp-server/recruitment-mcp-server/server/mcp_server.py）。请设置 HANDAAS_MCP_SERVER_ROOT 或 RECRUITMENT_MCP_URL。"}

    config = load_config(allow_example=allow_placeholders)
    if not modes["remote_mcp"]["ok"] and not modes["local_mcp"]["ok"]:
        errors.append("既未配置 Remote MCP URL，也未能定位本地 MCP server。")

    ok = not errors
    return {
        "ok": ok,
        "errors": errors,
        "warnings": warnings,
        "modes": modes,
        "config_redacted": redact(config) if config else {},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate recruitment-report MCP connection config.")
    parser.add_argument("--config", help="Optional config JSON path.")
    parser.add_argument("--allow-placeholders", action="store_true", help="Allow example placeholder values.")
    args = parser.parse_args()

    try:
        result = validate(allow_placeholders=args.allow_placeholders)
    except ConfigError as exc:
        print_json({"ok": False, "errors": [str(exc)], "warnings": []})
        raise SystemExit(1)
    print_json(result)
    if not result["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
