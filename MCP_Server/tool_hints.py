"""Behaviour hints (MCP tool annotations) shared by every AbletonMCP tool.

Clients use these to decide what needs confirmation and what is safe to call
freely, so the hints must stay accurate rather than optimistic:

``READ_ONLY``
    Reads Live state and changes nothing. Safe to retry, safe to call in bulk.

``WRITE``
    Changes the set but can be redone with undo, and repeating it is harmless
    (creating a track twice is not, so that stays a plain write).

``WRITE_IDEMPOTENT``
    A setter: calling it twice with the same arguments leaves the same result.

``DESTRUCTIVE``
    Removes or irreversibly replaces data (deletes, clears, flattens, replaces
    note content). Clients should confirm these with the user first.
"""

from mcp.types import ToolAnnotations

READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True)

WRITE = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False)

WRITE_IDEMPOTENT = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True)

DESTRUCTIVE = ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False)


def hint_for(tool_name: str) -> ToolAnnotations:
    """Pick a hint from a tool name, for tools with no hand-written annotation.

    Conservative on purpose: an unrecognised name is reported as a write, never
    as read-only, so a client cannot mistake a mutation for a safe read.
    """
    name = tool_name.lower()
    if name in _EXTRA_READ_ONLY:
        return READ_ONLY
    if name.startswith(("get_", "is_", "list_", "search_", "browse_", "describe_")):
        return READ_ONLY
    if name.startswith(("delete_", "remove_", "clear_")) or name in _EXTRA_DESTRUCTIVE:
        return DESTRUCTIVE
    if name.startswith(("set_", "toggle_")):
        return WRITE_IDEMPOTENT
    return WRITE


# Tools whose names do not follow the prefix conventions above.
_EXTRA_READ_ONLY = frozenset({
    "health_check",
    "get_playback_position",
    "get_session_info",
    "get_cpu_load",
    "get_all_track_names",
    "get_master_info",
    "get_warp_markers",
    "get_drum_rack_pads",
    "get_rack_macros",
    "get_groove_pool",
    "get_count_in_duration",
})

_EXTRA_DESTRUCTIVE = frozenset({
    "flatten_track",
    "ungroup_tracks",
    "unarm_all",
    "stop_all_clips",
    "transpose_notes",
    "humanize_clip_timing",
    "humanize_clip_velocity",
    "quantize_clip_notes",
})
