"""MCP wrappers for the bridge commands in AbletonMCP_Remote_Script/enableton_commands.py.

get_session_snapshot already exists in enableton_tools and calls the new command
when the Remote Script provides it. The other 41 names are registered here.
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import Context

from .enableton_tools import _call, _json
from .tool_hints import DESTRUCTIVE, READ_ONLY, WRITE, WRITE_IDEMPOTENT


REGISTERED: list = []


def _expose(annotation):
    def deco(fn):
        fn._gap_annotation = annotation
        REGISTERED.append(fn)
        return fn
    return deco


def register_gap_commands(mcp) -> int:
    """Register the gap-command tools. Returns how many were added."""
    for fn in REGISTERED:
        mcp.tool(annotations=fn._gap_annotation)(fn)
    return len(REGISTERED)


WRITE_COMMANDS = frozenset({
    "batch",
    "capture_and_insert_scene",
    "clip_op",
    "create_audio_clip",
    "create_take_lane",
    "delete_arrangement_clip",
    "duplicate_clip_to",
    "duplicate_session_clip_to_arrangement",
    "jump_to_locator",
    "load_device_to_master",
    "load_device_to_return",
    "preview_browser_item",
    "rack_variation",
    "replace_simpler_sample",
    "set_ableton_link",
    "set_clip_audio",
    "set_clip_groove",
    "set_clip_signature",
    "set_crossfade_assign",
    "set_device_enabled",
    "set_device_routing",
    "set_drum_pad",
    "set_fold_state",
    "set_loop",
    "set_record_mode",
    "set_send",
    "set_session_record",
    "set_simpler_playback_mode",
    "set_song_scale",
    "set_time_signature",
    "set_track_routing",
    "stop_browser_preview",
    "switch_to_arrangement_view",
    "trigger_session_record",
    "try_save_project",
    "write_automation",
})


# --------------------------------------------------------------------------
# Reads
# --------------------------------------------------------------------------

@_expose(READ_ONLY)
def get_arrangement_clips(ctx: Context, track_index: int) -> str:
    """List Arrangement clips on a track in time order: name, start, end, length, type."""
    return _json(_call("get_arrangement_clips", {"track_index": track_index}))


@_expose(READ_ONLY)
def get_device_routing(ctx: Context, track_index: int, device_index: int = 0, chain_index: int | None = None, chain_device_index: int | None = None) -> str:
    """Read a device's audio/MIDI bus routing, plus Compressor sidechain routing when present."""
    params: dict[str, Any] = {"track_index": track_index, "device_index": device_index}
    if chain_index is not None:
        params["chain_index"] = chain_index
        params["chain_device_index"] = chain_device_index or 0
    return _json(_call("get_device_routing", params))


@_expose(READ_ONLY)
def get_master_device_parameters(ctx: Context, device_index: int = 0) -> str:
    """Parameters of a device on the master track."""
    return _json(_call("get_master_device_parameters", {"device_index": device_index}))


@_expose(READ_ONLY)
def get_master_meters(ctx: Context) -> str:
    """Master input and output meters, each 0.0 to 1.0."""
    return _json(_call("get_master_meters"))


@_expose(READ_ONLY)
def get_return_device_parameters(ctx: Context, return_index: int, device_index: int = 0) -> str:
    """Parameters of a device on a return track."""
    return _json(_call("get_return_device_parameters", {"return_index": return_index, "device_index": device_index}))


# --------------------------------------------------------------------------
# Arrangement and clips
# --------------------------------------------------------------------------

@_expose(DESTRUCTIVE)
def delete_arrangement_clip(ctx: Context, track_index: int, arrangement_index: int | None = None, start_time: float | None = None) -> str:
    """Delete one Arrangement clip by index or by its start time in beats."""
    params: dict[str, Any] = {"track_index": track_index}
    if arrangement_index is not None:
        params["arrangement_index"] = arrangement_index
    if start_time is not None:
        params["start_time"] = start_time
    return _json(_call("delete_arrangement_clip", params))


@_expose(WRITE)
def duplicate_clip_to(ctx: Context, track_index: int, clip_index: int, target_track_index: int, target_clip_index: int) -> str:
    """Duplicate a Session clip into another slot, replacing whatever is there."""
    return _json(_call("duplicate_clip_to", {
        "track_index": track_index,
        "clip_index": clip_index,
        "target_track_index": target_track_index,
        "target_clip_index": target_clip_index,
    }))


@_expose(WRITE)
def duplicate_session_clip_to_arrangement(ctx: Context, track_index: int, clip_index: int, destination_time: float) -> str:
    """Copy a Session clip onto the Arrangement at destination_time beats."""
    return _json(_call("duplicate_session_clip_to_arrangement", {
        "track_index": track_index,
        "clip_index": clip_index,
        "destination_time": destination_time,
    }))


@_expose(WRITE)
def create_audio_clip(ctx: Context, track_index: int, file_path: str, clip_index: int | None = None, position: float | None = None, name: str | None = None, arrangement: bool = False) -> str:
    """Create an audio clip from an absolute path. Session needs clip_index. Arrangement needs position."""
    params: dict[str, Any] = {"track_index": track_index, "file_path": file_path, "arrangement": arrangement}
    if clip_index is not None:
        params["clip_index"] = clip_index
    if position is not None:
        params["position"] = position
    if name is not None:
        params["name"] = name
    return _json(_call("create_audio_clip", params))


@_expose(DESTRUCTIVE)
def set_clip_audio(ctx: Context, track_index: int, clip_index: int, file_path: str | None = None, gain: float | None = None, pitch_coarse: int | None = None, pitch_fine: float | None = None, warping: bool | None = None, warp_mode: int | None = None, ram_mode: bool | None = None, name: str | None = None) -> str:
    """Replace a slot's audio file and/or set gain, pitch, warp, or RAM mode."""
    params: dict[str, Any] = {"track_index": track_index, "clip_index": clip_index}
    for key, value in (
        ("file_path", file_path), ("gain", gain), ("pitch_coarse", pitch_coarse),
        ("pitch_fine", pitch_fine), ("warping", warping), ("warp_mode", warp_mode),
        ("ram_mode", ram_mode), ("name", name),
    ):
        if value is not None:
            params[key] = value
    return _json(_call("set_clip_audio", params))


@_expose(WRITE)
def create_take_lane(ctx: Context, track_index: int, name: str | None = None) -> str:
    """Create an Arrangement take lane on a track."""
    params: dict[str, Any] = {"track_index": track_index}
    if name is not None:
        params["name"] = name
    return _json(_call("create_take_lane", params))


@_expose(DESTRUCTIVE)
def clip_op(ctx: Context, track_index: int, clip_index: int, operation: str, region_start: float | None = None, region_length: float | None = None, destination_time: float | None = None, pitch: int | None = None, transposition_amount: int | None = None, grid: int | None = None, amount: float | None = None, muted: bool | None = None, name: str | None = None, color: int | None = None, looping: bool | None = None, loop_start: float | None = None, loop_end: float | None = None, gain: float | None = None, pitch_coarse: int | None = None, pitch_fine: float | None = None, warping: bool | None = None, warp_mode: int | None = None, start_marker: float | None = None, end_marker: float | None = None, ram_mode: bool | None = None) -> str:
    """Run one clip operation: crop, duplicate_loop, duplicate_region, quantize, select_all_notes, deselect_all_notes, mute, name, color, looping, gain, pitch, warp, markers, ram_mode."""
    params: dict[str, Any] = {"track_index": track_index, "clip_index": clip_index, "operation": operation}
    for key, value in (
        ("region_start", region_start), ("region_length", region_length),
        ("destination_time", destination_time), ("pitch", pitch),
        ("transposition_amount", transposition_amount), ("grid", grid),
        ("amount", amount), ("muted", muted), ("name", name), ("color", color),
        ("looping", looping), ("loop_start", loop_start), ("loop_end", loop_end),
        ("gain", gain), ("pitch_coarse", pitch_coarse), ("pitch_fine", pitch_fine),
        ("warping", warping), ("warp_mode", warp_mode),
        ("start_marker", start_marker), ("end_marker", end_marker), ("ram_mode", ram_mode),
    ):
        if value is not None:
            params[key] = value
    return _json(_call("clip_op", params))


@_expose(WRITE_IDEMPOTENT)
def set_clip_groove(ctx: Context, track_index: int, clip_index: int, groove_name: str | None = None, groove_index: int | None = None) -> str:
    """Assign a groove-pool groove to a clip by name or index."""
    params: dict[str, Any] = {"track_index": track_index, "clip_index": clip_index}
    if groove_name is not None:
        params["groove_name"] = groove_name
    if groove_index is not None:
        params["groove_index"] = groove_index
    return _json(_call("set_clip_groove", params))


@_expose(WRITE_IDEMPOTENT)
def set_clip_signature(ctx: Context, track_index: int, clip_index: int, numerator: int, denominator: int) -> str:
    """Set a clip's time signature."""
    return _json(_call("set_clip_signature", {
        "track_index": track_index, "clip_index": clip_index,
        "numerator": numerator, "denominator": denominator,
    }))


@_expose(WRITE)
def write_automation(ctx: Context, track_index: int, clip_index: int, points: list[dict[str, float]], parameter_name: str | None = None, device_index: int | None = None, parameter_index: int | None = None, clear: bool = True) -> str:
    """Write clip automation breakpoints. points are {time, value} in beats and raw parameter units."""
    params: dict[str, Any] = {
        "track_index": track_index, "clip_index": clip_index,
        "points": points, "clear": clear,
    }
    if parameter_name is not None:
        params["parameter_name"] = parameter_name
    if device_index is not None:
        params["device_index"] = device_index
    if parameter_index is not None:
        params["parameter_index"] = parameter_index
    return _json(_call("write_automation", params))


# --------------------------------------------------------------------------
# Devices
# --------------------------------------------------------------------------

@_expose(WRITE)
def load_device_to_master(ctx: Context, device_name: str | None = None, item_uri: str | None = None, index: int | None = None) -> str:
    """Load a native device by name (Live 12.3+) or a browser item onto the master track."""
    params: dict[str, Any] = {}
    if device_name is not None:
        params["device_name"] = device_name
    if item_uri is not None:
        params["item_uri"] = item_uri
    if index is not None:
        params["index"] = index
    return _json(_call("load_device_to_master", params))


@_expose(WRITE)
def load_device_to_return(ctx: Context, return_index: int, device_name: str | None = None, item_uri: str | None = None, index: int | None = None) -> str:
    """Load a native device by name (Live 12.3+) or a browser item onto a return track."""
    params: dict[str, Any] = {"return_index": return_index}
    if device_name is not None:
        params["device_name"] = device_name
    if item_uri is not None:
        params["item_uri"] = item_uri
    if index is not None:
        params["index"] = index
    return _json(_call("load_device_to_return", params))


@_expose(WRITE_IDEMPOTENT)
def set_device_enabled(ctx: Context, track_index: int, device_index: int, enabled: bool) -> str:
    """Turn a device on or off."""
    return _json(_call("set_device_enabled", {
        "track_index": track_index, "device_index": device_index, "enabled": enabled,
    }))


@_expose(WRITE_IDEMPOTENT)
def set_device_routing(ctx: Context, track_index: int, device_index: int = 0, routing_type: str | None = None, routing_channel: str | None = None, input_type: str | None = None, input_channel: str | None = None, bus: str | None = None, bus_index: int | None = None) -> str:
    """Set a device bus route or a Compressor sidechain route, by name or index."""
    params: dict[str, Any] = {"track_index": track_index, "device_index": device_index}
    for key, value in (
        ("routing_type", routing_type), ("routing_channel", routing_channel),
        ("input_type", input_type), ("input_channel", input_channel),
        ("bus", bus), ("bus_index", bus_index),
    ):
        if value is not None:
            params[key] = value
    return _json(_call("set_device_routing", params))


@_expose(WRITE)
def rack_variation(ctx: Context, track_index: int, device_index: int, action: str = "store", index: int | None = None) -> str:
    """Rack macro variation. action is store, select, recall, recall_last, or delete."""
    params: dict[str, Any] = {"track_index": track_index, "device_index": device_index, "action": action}
    if index is not None:
        params["index"] = index
    return _json(_call("rack_variation", params))


@_expose(WRITE_IDEMPOTENT)
def set_simpler_playback_mode(ctx: Context, track_index: int, mode: str, device_index: int | None = None) -> str:
    """Set Simpler playback mode: classic, one-shot, slicing, or 0, 1, 2."""
    params: dict[str, Any] = {"track_index": track_index, "mode": mode}
    if device_index is not None:
        params["device_index"] = device_index
    return _json(_call("set_simpler_playback_mode", params))


@_expose(DESTRUCTIVE)
def replace_simpler_sample(ctx: Context, track_index: int, file_path: str | None = None, item_uri: str | None = None, device_index: int | None = None) -> str:
    """Replace the sample in a Simpler, from a file path when Live allows it, or from a browser item_uri."""
    params: dict[str, Any] = {"track_index": track_index}
    if file_path is not None:
        params["file_path"] = file_path
    if item_uri is not None:
        params["item_uri"] = item_uri
    if device_index is not None:
        params["device_index"] = device_index
    return _json(_call("replace_simpler_sample", params))


@_expose(WRITE_IDEMPOTENT)
def set_drum_pad(ctx: Context, track_index: int, device_index: int, pad_index: int, mute: bool | None = None, solo: bool | None = None, name: str | None = None) -> str:
    """Set a Drum Rack pad mute, solo, or chain name. pad_index is the MIDI note."""
    params: dict[str, Any] = {
        "track_index": track_index, "device_index": device_index, "pad_index": pad_index,
    }
    if mute is not None:
        params["mute"] = mute
    if solo is not None:
        params["solo"] = solo
    if name is not None:
        params["name"] = name
    return _json(_call("set_drum_pad", params))


# --------------------------------------------------------------------------
# Mixer, song, transport, browser
# --------------------------------------------------------------------------

@_expose(WRITE_IDEMPOTENT)
def set_crossfade_assign(ctx: Context, track_index: int, assign: str) -> str:
    """Set a track's crossfade assign to A, none, or B."""
    return _json(_call("set_crossfade_assign", {"track_index": track_index, "assign": assign}))


@_expose(WRITE_IDEMPOTENT)
def set_send(ctx: Context, track_index: int, send_index: int, value: float) -> str:
    """Set one send level. value is clamped to that send's range."""
    return _json(_call("set_send", {"track_index": track_index, "send_index": send_index, "value": value}))


@_expose(WRITE_IDEMPOTENT)
def set_fold_state(ctx: Context, track_index: int, folded: bool) -> str:
    """Fold or unfold a group track. Other tracks collapse in the Arrangement."""
    return _json(_call("set_fold_state", {"track_index": track_index, "folded": folded}))


@_expose(WRITE_IDEMPOTENT)
def set_track_routing(ctx: Context, track_index: int, input_type: str | None = None, input_channel: str | None = None, output_type: str | None = None, output_channel: str | None = None) -> str:
    """Set track input or output routing by display name, identifier, or index."""
    params: dict[str, Any] = {"track_index": track_index}
    for key, value in (
        ("input_type", input_type), ("input_channel", input_channel),
        ("output_type", output_type), ("output_channel", output_channel),
    ):
        if value is not None:
            params[key] = value
    return _json(_call("set_track_routing", params))


@_expose(WRITE_IDEMPOTENT)
def set_loop(ctx: Context, enabled: bool | None = None, start: float | None = None, length: float | None = None) -> str:
    """Set the Arrangement loop on/off, start, and length in beats."""
    params: dict[str, Any] = {}
    if enabled is not None:
        params["enabled"] = enabled
    if start is not None:
        params["start"] = start
    if length is not None:
        params["length"] = length
    return _json(_call("set_loop", params))


@_expose(WRITE_IDEMPOTENT)
def set_time_signature(ctx: Context, numerator: int, denominator: int) -> str:
    """Set the song time signature."""
    return _json(_call("set_time_signature", {"numerator": numerator, "denominator": denominator}))


@_expose(WRITE_IDEMPOTENT)
def set_song_scale(ctx: Context, scale_name: str | None = None, root_note: int | None = None, scale_mode: bool | None = None) -> str:
    """Set the song scale name, root note (0=C through 11=B), or scale-mode highlighting."""
    params: dict[str, Any] = {}
    if scale_name is not None:
        params["scale_name"] = scale_name
    if root_note is not None:
        params["root_note"] = root_note
    if scale_mode is not None:
        params["scale_mode"] = scale_mode
    return _json(_call("set_song_scale", params))


@_expose(WRITE_IDEMPOTENT)
def set_record_mode(ctx: Context, enabled: bool) -> str:
    """Set the Arrangement Record button."""
    return _json(_call("set_record_mode", {"enabled": enabled}))


@_expose(WRITE_IDEMPOTENT)
def set_session_record(ctx: Context, enabled: bool) -> str:
    """Set the Session record button."""
    return _json(_call("set_session_record", {"enabled": enabled}))


@_expose(WRITE)
def trigger_session_record(ctx: Context, record_length: float | None = None) -> str:
    """Start session recording. record_length in beats stops it automatically."""
    params: dict[str, Any] = {}
    if record_length is not None:
        params["record_length"] = record_length
    return _json(_call("trigger_session_record", params))


@_expose(WRITE_IDEMPOTENT)
def set_ableton_link(ctx: Context, enabled: bool | None = None, start_stop_sync: bool | None = None) -> str:
    """Toggle Ableton Link and, optionally, Link start/stop sync."""
    params: dict[str, Any] = {}
    if enabled is not None:
        params["enabled"] = enabled
    if start_stop_sync is not None:
        params["start_stop_sync"] = start_stop_sync
    return _json(_call("set_ableton_link", params))


@_expose(WRITE_IDEMPOTENT)
def jump_to_locator(ctx: Context, index: int | None = None, name: str | None = None, time: float | None = None) -> str:
    """Jump the playhead to a locator by index, name, or time in beats."""
    params: dict[str, Any] = {}
    if index is not None:
        params["index"] = index
    if name is not None:
        params["name"] = name
    if time is not None:
        params["time"] = time
    return _json(_call("jump_to_locator", params))


@_expose(WRITE_IDEMPOTENT)
def switch_to_arrangement_view(ctx: Context) -> str:
    """Show and focus the Arrangement view."""
    return _json(_call("switch_to_arrangement_view"))


@_expose(WRITE)
def capture_and_insert_scene(ctx: Context) -> str:
    """Capture the playing Session clips into a new scene under the selected scene."""
    return _json(_call("capture_and_insert_scene"))


@_expose(WRITE)
def try_save_project(ctx: Context) -> str:
    """Save the Live set when this Live version exposes a save method."""
    return _json(_call("try_save_project"))


@_expose(WRITE)
def preview_browser_item(ctx: Context, item_uri: str) -> str:
    """Audition a browser item. Call stop_browser_preview to stop it."""
    return _json(_call("preview_browser_item", {"item_uri": item_uri}))


@_expose(WRITE_IDEMPOTENT)
def stop_browser_preview(ctx: Context) -> str:
    """Stop browser audition playback."""
    return _json(_call("stop_browser_preview"))


@_expose(DESTRUCTIVE)
def batch(ctx: Context, commands: list[dict[str, Any]], stop_on_error: bool = True, undo_on_error: bool = True) -> str:
    """Run up to 32 bridge commands as one undo step. Each entry is {type, params}. Nested batch is rejected."""
    return _json(_call("batch", {
        "commands": commands,
        "stop_on_error": stop_on_error,
        "undo_on_error": undo_on_error,
    }))
