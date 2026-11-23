#!/usr/bin/env python3
"""classify_enableton_tools.py - what of Enableton's catalogue can live in this repo?

Compares Enableton's published tool catalogue against:
  * the MCP tools this repo already exposes (duplicates to ignore),
  * the tools ported in MCP_Server/enableton_tools.py,
  * the commands AbletonMCP_Remote_Script/__init__.py implements.

Usage:
    python scripts/classify_enableton_tools.py PATH/TO/tool-catalog.json
    python scripts/classify_enableton_tools.py catalog.json --upstream-map upstream_map.json --json out.json

The upstream map (tool name -> bridge commands) can be produced from
mcp-server-ableton-live's tools modules; without it the script reports only
duplicate / ported / unported counts.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def our_tool_names() -> set[str]:
    names: set[str] = set()
    server = (REPO_ROOT / "MCP_Server" / "server.py").read_text(encoding="utf-8", errors="ignore")
    names.update(re.findall(r"@mcp\.tool\([^)]*\)\s*\ndef\s+(\w+)", server))
    ported = (REPO_ROOT / "MCP_Server" / "enableton_tools.py").read_text(encoding="utf-8", errors="ignore")
    block = re.search(r"REGISTERED_TOOLS\s*=\s*\((.*?)\)", ported, re.S)
    if block:
        names.update(re.findall(r"(\w+)", block.group(1)))
    return names


def our_commands() -> set[str]:
    script = (REPO_ROOT / "AbletonMCP_Remote_Script" / "__init__.py").read_text(
        encoding="utf-8", errors="ignore"
    )
    return set(re.findall(r'command_type\s*==\s*"([a-z0-9_]+)"', script))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("catalog", help="Enableton docs/tool-catalog.json")
    parser.add_argument("--upstream-map", help="JSON of tool name -> bridge commands")
    parser.add_argument("--json", dest="json_out", help="write the full report here")
    parser.add_argument("--list", action="store_true", help="list every tool name per bucket")
    args = parser.parse_args(argv)

    catalog_path = Path(args.catalog)
    if not catalog_path.is_file():
        raise SystemExit(f"error: catalogue not found: {catalog_path}")
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    tools = catalog["tools"]

    ours = our_tool_names()
    commands = our_commands()

    upstream_map: dict[str, list[str]] = {}
    if args.upstream_map:
        upstream_map = json.loads(Path(args.upstream_map).read_text(encoding="utf-8"))

    duplicates, ported, portable, blocked = [], [], [], []
    missing_commands: set[str] = set()

    for tool in tools:
        name = tool["name"]
        if name in ours:
            duplicates.append(name)
            continue
        needed = upstream_map.get(name)
        if needed is None:
            portable.append(name)  # no bridge mapping known: needs manual review
            continue
        if not needed:
            portable.append(name)
            continue
        absent = [c for c in needed if c not in commands]
        if absent:
            blocked.append({"tool": name, "missing": absent})
            missing_commands.update(absent)
        else:
            portable.append(name)

    report = {
        "enableton_version": catalog.get("enableton_version"),
        "upstream_version": catalog.get("upstream_version"),
        "catalog_tools": len(tools),
        "already_exposed_here": len(duplicates),
        "portable_now": len(portable),
        "blocked_on_live_side": len(blocked),
        "missing_commands": sorted(missing_commands),
        "details": {
            "duplicates": sorted(duplicates),
            "portable": sorted(portable),
            "blocked": blocked,
        },
    }

    print(f"catalogue tools      : {len(tools)}")
    print(f"already exposed here : {len(duplicates)}  (ignored)")
    print(f"runnable with today's bridge / no bridge call: {len(portable)}")
    print(f"needs new live-side commands: {len(blocked)}")
    if missing_commands:
        print(f"distinct commands to implement: {len(missing_commands)}")

    if args.json_out:
        Path(args.json_out).write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"report written to {args.json_out}")

    if args.list:
        for title, items in (
            ("duplicates", sorted(duplicates)),
            ("portable", sorted(portable)),
            ("blocked", [f"{b['tool']} (needs {', '.join(b['missing'])})" for b in blocked]),
        ):
            print(f"\n== {title} ({len(items)}) ==")
            for item in items:
                print(f"  {item}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
