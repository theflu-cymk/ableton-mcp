#!/usr/bin/env python3
"""apply_tool_hints.py - annotate every MCP tool in MCP_Server/server.py.

Rewrites bare ``@mcp.tool()`` decorators into
``@mcp.tool(annotations=<HINT>)`` using the prefix rules in
``MCP_Server/tool_hints.py`` (read-only gets ``READ_ONLY``, ``delete_``/
``remove_``/``clear_`` get ``DESTRUCTIVE``, setters get ``WRITE_IDEMPOTENT``,
everything else is a plain ``WRITE``). Idempotent: already-annotated tools are
left alone.

Usage:
    python scripts/apply_tool_hints.py [--check]
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SERVER = REPO_ROOT / "MCP_Server" / "server.py"
IMPORT_LINE = "from .tool_hints import DESTRUCTIVE, READ_ONLY, WRITE, WRITE_IDEMPOTENT\n"

PATTERN = re.compile(r"@mcp\.tool\(\)(\s*\n\s*def\s+(\w+)\s*\()")


def hint_name(tool: str) -> str:
    """Mirror MCP_Server/tool_hints.hint_for() without importing mcp."""
    extra_read = {
        "health_check", "get_playback_position", "get_session_info", "get_cpu_load",
        "get_all_track_names", "get_master_info", "get_warp_markers", "get_drum_rack_pads",
        "get_rack_macros", "get_groove_pool", "get_count_in_duration",
    }
    extra_destructive = {
        "flatten_track", "ungroup_tracks", "unarm_all", "stop_all_clips", "transpose_notes",
        "humanize_clip_timing", "humanize_clip_velocity", "quantize_clip_notes",
    }
    name = tool.lower()
    if name in extra_read:
        return "READ_ONLY"
    if name.startswith(("get_", "is_", "list_", "search_", "browse_", "describe_")):
        return "READ_ONLY"
    if name.startswith(("delete_", "remove_", "clear_")) or name in extra_destructive:
        return "DESTRUCTIVE"
    if name.startswith(("set_", "toggle_")):
        return "WRITE_IDEMPOTENT"
    return "WRITE"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="report without writing")
    args = parser.parse_args(argv)

    source = SERVER.read_text(encoding="utf-8")
    if IMPORT_LINE.strip() not in source:
        anchor = "from mcp.server.fastmcp import FastMCP, Context\n"
        if anchor not in source:
            raise SystemExit("error: could not find the FastMCP import to anchor the hint import")
        source = source.replace(anchor, anchor + "\n" + IMPORT_LINE, 1)

    counts: dict[str, int] = {}

    def replace(match: re.Match) -> str:
        tool = match.group(2)
        hint = hint_name(tool)
        counts[hint] = counts.get(hint, 0) + 1
        return f"@mcp.tool(annotations={hint}){match.group(1)}"

    updated, total = PATTERN.subn(replace, source)

    print(f"annotated {total} bare @mcp.tool() decorators")
    for hint in sorted(counts):
        print(f"  {hint:<18} {counts[hint]}")

    if args.check:
        return 0
    if total or IMPORT_LINE.strip() not in SERVER.read_text(encoding="utf-8"):
        SERVER.write_text(updated, encoding="utf-8")
        print(f"wrote {SERVER}")
    else:
        print("nothing to change")
    return 0


if __name__ == "__main__":
    sys.exit(main())
