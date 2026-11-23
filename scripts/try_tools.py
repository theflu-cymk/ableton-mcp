#!/usr/bin/env python3
"""try_tools.py - exercise the Enableton-ported tools against a running Ableton Live.

The tools talk to Live exactly as the MCP server does: through the AbletonMCP
Remote Script's socket on port 9877. Nothing here is mocked, so a green run means
the bridge, the command and the tool are all working.

Usage:
    python scripts/try_tools.py                # read-only demo of the ported tools
    python scripts/try_tools.py --list         # names and parameters of the ported tools
    python scripts/try_tools.py --call get_track_meters track_index=0
    python scripts/try_tools.py --call humanize_clip track_index=0 clip_index=0 timing=0.02

Before this can connect:
    1. Live is open, and Settings > Link, Tempo & MIDI > Control Surface says "AbletonMCP"
       (Input/Output: None). Live only scans Remote Scripts at startup, so restart Live
       if "AbletonMCP" is not in the dropdown.
    2. Nothing else owns port 9877.
"""

from __future__ import annotations

import argparse
import inspect
import json
import socket
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from MCP_Server import enableton_tools as et  # noqa: E402
from MCP_Server.server import ABLETON_HOST, ABLETON_PORT, get_ableton_connection  # noqa: E402


def bridge_is_up() -> bool:
    sock = socket.socket()
    sock.settimeout(1.5)
    try:
        sock.connect((ABLETON_HOST, ABLETON_PORT))
        return True
    except OSError:
        return False
    finally:
        sock.close()


def explain_down() -> None:
    print(f"No bridge on {ABLETON_HOST}:{ABLETON_PORT}, so Live cannot be reached yet.\n")
    print("Do this in Ableton Live:")
    print("  1. Settings > Link, Tempo & MIDI")
    print('  2. Control Surface: choose "AbletonMCP"; Input: None; Output: None')
    print("  3. If AbletonMCP is not in the list, restart Live - it only scans")
    print("     Remote Scripts at startup and the script was installed while it was open.")
    print("\nCheck the script is in place:")
    print("  %USERPROFILE%\\Documents\\Ableton\\User Library\\Remote Scripts\\AbletonMCP\\__init__.py")


def _run(label: str, function, **kwargs):
    try:
        result = function(None, **kwargs)
        payload = json.loads(result)
        print(f"[ok]   {label}")
        print(json.dumps(payload, indent=2)[:1400])
    except Exception as exc:  # a failed tool must not stop the demo
        print(f"[skip] {label}: {type(exc).__name__}: {exc}")
    print("-" * 70)


def demo() -> int:
    print(f"Connected to Live at {ABLETON_HOST}:{ABLETON_PORT}\n")
    _run("health_check", et.__dict__.get("continue_playing", None) or (lambda *a, **k: et._json(et._call("health_check"))))
    _run("get_session_snapshot()", et.get_session_snapshot)
    _run("get_scale_info()", et.get_scale_info)
    _run("get_grooves()", et.get_grooves)
    _run("get_track_meters(track_index=0)", et.get_track_meters, track_index=0)

    track = et._call("get_track_info", {"track_index": 0})
    slots = track.get("clip_slots", []) if isinstance(track, dict) else []
    for slot in slots:
        if slot.get("has_clip"):
            index = slot.get("index")
            _run(f"get_clip_info(track_index=0, clip_index={index})", et.get_clip_info, track_index=0, clip_index=index)
            _run(f"detect_clip_key(track_index=0, clip_index={index})", et.detect_clip_key, track_index=0, clip_index=index)
            break
    _run("detect_track_key(track_index=0)", et.detect_track_key, track_index=0)
    return 0


def list_tools() -> int:
    for function in et.REGISTERED_TOOLS:
        signature = inspect.signature(function)
        params = [p for p in signature.parameters if p != "ctx"]
        hint = et.TOOL_HINTS.get(function.__name__)
        if hint and hint.readOnlyHint:
            kind = "read-only"
        elif hint and hint.destructiveHint:
            kind = "destructive"
        elif hint and hint.idempotentHint:
            kind = "idempotent write"
        else:
            kind = "write"
        first = (function.__doc__ or "").strip().splitlines()[0]
        print(f"{function.__name__:<28} [{kind:<11}] ({', '.join(params) or 'no params'})")
        print(f"    {first}")
    print(f"\n{len(et.REGISTERED_TOOLS)} ported tools")
    return 0


def call(name: str, pairs: list[str]) -> int:
    function = next((f for f in et.REGISTERED_TOOLS if f.__name__ == name), None)
    if function is None:
        print(f"error: '{name}' is not a ported tool. Use --list.")
        return 2
    signature = inspect.signature(function)
    kwargs = {}
    for pair in pairs:
        if "=" not in pair:
            print(f"error: expected key=value, got '{pair}'")
            return 2
        key, _, raw = pair.partition("=")
        try:
            value = json.loads(raw)
        except json.JSONDecodeError:
            value = raw
        if key not in signature.parameters:
            print(f"error: {name} has no parameter '{key}'; params are {[p for p in signature.parameters if p != 'ctx']}")
            return 2
        kwargs[key] = value
    _run(f"{name}({', '.join(f'{k}={v!r}' for k, v in kwargs.items())})", function, **kwargs)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Try the AbletonMCP / Enableton tools against Live.")
    parser.add_argument("--list", action="store_true", help="list ported tools and their parameters")
    parser.add_argument("--call", metavar="TOOL", help="call one ported tool")
    parser.add_argument("args", nargs="*", help="key=value arguments for --call")
    options = parser.parse_args(argv)

    if options.list:
        return list_tools()

    if not bridge_is_up():
        explain_down()
        return 1

    if options.call:
        return call(options.call, options.args)

    return demo()


if __name__ == "__main__":
    sys.exit(main())
