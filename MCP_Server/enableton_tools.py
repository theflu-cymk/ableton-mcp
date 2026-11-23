"""Typed tools ported from Enableton's tool catalogue (enableton 0.1.0b2 / upstream 1.8.1).

Enableton publishes a machine-readable catalogue of its 242 tools at
``docs/tool-catalog.json`` in the EnAbleton repository. 50 of those names already
exist in this repo (see docs/ENABLETON_PORT.md), so they are not repeated here.

This module implements the subset whose live-side action the bundled
``AbletonMCP_Remote_Script`` already supports, so the tools work against an
unmodified server. Every tool returns a JSON string. Tools that require commands
this Remote Script does not implement (arrangement clip editing, track meters,
nested-device routing, warp repair, offline .als analysis, ...) are deliberately
absent and tracked in docs/ENABLETON_PORT.md.
"""

from __future__ import annotations

import json
import random
from typing import Any, Dict, List

from mcp.server.fastmcp import Context

from .tool_hints import DESTRUCTIVE, READ_ONLY, WRITE, WRITE_IDEMPOTENT


def _ableton():
    """Late import so this module can be registered from within server.py."""
    from .server import get_ableton_connection

    return get_ableton_connection()


def _call(command: str, params: Dict[str, Any] | None = None) -> Any:
    return _ableton().send_command(command, params or {})


def _json(payload: Any) -> str:
    return json.dumps(payload, indent=2)


# ============================================================================
# Clip note helpers
# ============================================================================

# Beats per grid step, as accepted by the remote script's quantize_clip command.
QUANTIZE_GRIDS: Dict[str, float] = {
    "quarter": 1.0,
    "eighth": 0.5,
    "eighth_triplet": 1.0 / 3.0,
    "sixteenth": 0.25,
    "sixteenth_triplet": 1.0 / 6.0,
    "thirtysecond": 0.125,
}

PITCH_CLASSES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

# Krumhansl-Kessler key profiles.
KK_MAJOR = [6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88]
KK_MINOR = [6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17]


def _notes_of(result: Any) -> List[Dict[str, Any]]:
    """Normalise whatever the bridge returned into a list of note dicts."""
    if isinstance(result, list):
        return [n for n in result if isinstance(n, dict)]
    if isinstance(result, dict):
        for key in ("notes", "result", "data"):
            value = result.get(key)
            if isinstance(value, list):
                return [n for n in value if isinstance(n, dict)]
    return []


def _correlate(histogram: List[float], profile: List[float]) -> float:
    n = len(histogram)
    mean_h = sum(histogram) / n
    mean_p = sum(profile) / n
    num = sum((histogram[i] - mean_h) * (profile[i] - mean_p) for i in range(n))
    den_h = sum((histogram[i] - mean_h) ** 2 for i in range(n)) ** 0.5
    den_p = sum((profile[i] - mean_p) ** 2 for i in range(n)) ** 0.5
    if den_h == 0 or den_p == 0:
        return 0.0
    return num / (den_h * den_p)


def _best_key(histogram: List[float], weight: str) -> Dict[str, Any]:
    """Pick the best fitting major/minor key for a 12-bin pitch-class histogram."""
    if sum(histogram) == 0:
        return {"key": None, "mode": None, "confidence": 0.0}

    best: Dict[str, Any] = {"key": None, "mode": None, "score": -2.0}
    runner_up = -2.0
    for root in range(12):
        for mode, profile in (("major", KK_MAJOR), ("minor", KK_MINOR)):
            rotated = [profile[(i - root) % 12] for i in range(12)]
            score = _correlate(histogram, rotated)
            if score > best["score"]:
                if best["key"] is not None:
                    runner_up = best["score"]
                best = {"key": PITCH_CLASSES[root], "mode": mode, "score": score}
            elif score > runner_up:
                runner_up = score

    return {
        "key": best["key"],
        "mode": best["mode"],
        "confidence": round(max(best["score"], 0.0), 4),
        "margin": round(max(best["score"] - max(runner_up, -1.0), 0.0), 4),
        "weight": weight,
    }


def _histogram_from_notes(notes: List[Dict[str, Any]], weight: str) -> List[float]:
    histogram = [0.0] * 12
    for note in notes:
        try:
            pitch = int(note.get("pitch", 0))
        except (TypeError, ValueError):
            continue
        if note.get("mute"):
            continue
        amount = 1.0
        if weight == "duration":
            try:
                amount = float(note.get("duration", 1.0)) or 1.0
            except (TypeError, ValueError):
                amount = 1.0
        histogram[pitch % 12] += amount
    return histogram


# ============================================================================
# Transport, groove and global settings
# ============================================================================

def continue_playing(ctx: Context) -> str:
    """Resume playback from the current position, unlike start_playback which restarts."""
    return _json(_call("continue_playing"))


def stop_all_clips(ctx: Context) -> str:
    """Stop every playing Session clip without stopping the transport."""
    return _json(_call("stop_all_clips"))


def tap_tempo(ctx: Context) -> str:
    """Tap the tempo once. Repeated taps at a steady beat set the session tempo."""
    return _json(_call("tap_tempo"))


def set_swing_amount(ctx: Context, amount: float) -> str:
    """Set the global swing amount used when quantizing with swing (0.0 to 1.0)."""
    if not 0.0 <= amount <= 1.0:
        raise ValueError("amount must be between 0.0 and 1.0")
    return _json(_call("set_swing_amount", {"amount": amount}))


def set_groove_amount(ctx: Context, amount: float) -> str:
    """Set the global Groove Amount (0.0 to 1.0), scaling how strongly applied grooves act."""
    if not 0.0 <= amount <= 1.0:
        raise ValueError("amount must be between 0.0 and 1.0")
    return _json(_call("set_groove_amount", {"amount": amount}))


def set_crossfader(ctx: Context, value: float) -> str:
    """Set the master crossfader: -1.0 full A, 0.0 center, 1.0 full B."""
    if not -1.0 <= value <= 1.0:
        raise ValueError("value must be between -1.0 and 1.0")
    return _json(_call("set_crossfader", {"value": value}))


def set_clip_trigger_quantization(ctx: Context, value: int) -> str:
    """Global launch quantization for clips and scenes: 0=None, 1=1/8, 2=1/4, 3=1/2, 4=1 bar."""
    if not 0 <= value <= 4:
        raise ValueError("value must be between 0 (None) and 4 (1 bar)")
    return _json(_call("set_clip_trigger_quantization", {"quantization": value}))


def set_session_automation_record(ctx: Context, enabled: bool) -> str:
    """Toggle recording parameter changes into Session clip envelopes."""
    return _json(_call("set_session_automation_record", {"enabled": enabled}))


def set_arrangement_overdub(ctx: Context, enabled: bool) -> str:
    """Toggle arrangement overdub so recording layers MIDI over existing material."""
    return _json(_call("set_arrangement_overdub", {"enabled": enabled}))


def re_enable_automation(ctx: Context) -> str:
    """Re-enable automation that manual parameter changes overrode."""
    return _json(_call("re_enable_automation"))


def set_arrangement_time(ctx: Context, time: float) -> str:
    """Move the arrangement playhead to a position in beats."""
    if time < 0:
        raise ValueError("time must be 0 or greater")
    return _json(_call("set_current_song_time", {"time": time}))


# ============================================================================
# Return tracks
# ============================================================================

def create_return_track(ctx: Context) -> str:
    """Create a new return track (a send bus, e.g. for a shared reverb or delay)."""
    return _json(_call("create_return_track"))


def delete_return_track(ctx: Context, return_index: int) -> str:
    """Delete a return track by index (0 = Return A). Later returns shift down."""
    if return_index < 0:
        raise ValueError("return_index must be 0 or greater")
    return _json(_call("delete_return_track", {"index": return_index}))


# ============================================================================
# Clip reading, quantization, humanizing and key detection
# ============================================================================

def get_clip_info(ctx: Context, track_index: int, clip_index: int) -> str:
    """Full clip state: name, type, length, loop points, start/end markers, color and playing state."""
    return _json(_call("get_clip_info", {"track_index": track_index, "clip_index": clip_index}))


def quantize_clip(
    ctx: Context,
    track_index: int,
    clip_index: int,
    grid: str = "sixteenth",
    amount: float = 1.0,
) -> str:
    """Quantize a MIDI clip.

    grid: quarter, eighth, eighth_triplet, sixteenth, sixteenth_triplet or thirtysecond.
    amount: 0.0 to 1.0 strength (1.0 snaps fully).
    """
    key = (grid or "sixteenth").lower()
    if key not in QUANTIZE_GRIDS:
        raise ValueError(f"grid must be one of {', '.join(sorted(QUANTIZE_GRIDS))}")
    if not 0.0 <= amount <= 1.0:
        raise ValueError("amount must be between 0.0 and 1.0")
    return _json(
        _call(
            "quantize_clip",
            {
                "track_index": track_index,
                "clip_index": clip_index,
                "quantize_to": QUANTIZE_GRIDS[key],
                "amount": amount,
            },
        )
    )


def humanize_clip(
    ctx: Context,
    track_index: int,
    clip_index: int,
    timing: float = 0.02,
    velocity: float = 8.0,
    seed: int | None = None,
) -> str:
    """Read a MIDI clip, jitter its note timing and velocity, and write it back.

    timing: maximum start-time shift in beats (0.02 is about a 32nd of a beat).
    velocity: maximum velocity shift in either direction.
    seed: optional RNG seed so a humanization can be repeated exactly.
    """
    if timing < 0 or velocity < 0:
        raise ValueError("timing and velocity must be 0 or greater")

    result = _call("get_clip_notes", {"track_index": track_index, "clip_index": clip_index})
    notes = _notes_of(result)
    if not notes:
        return _json({"humanized": 0, "reason": "clip has no notes or is not a MIDI clip"})

    rng = random.Random(seed)
    updated: List[Dict[str, Any]] = []
    for note in notes:
        start = float(note.get("start_time", 0.0)) + rng.uniform(-timing, timing)
        vel = int(round(float(note.get("velocity", 100)) + rng.uniform(-velocity, velocity)))
        updated.append(
            {
                "pitch": int(note.get("pitch", 60)),
                "start_time": round(max(start, 0.0), 6),
                "duration": float(note.get("duration", 0.25)),
                "velocity": max(1, min(127, vel)),
                "mute": bool(note.get("mute", False)),
            }
        )

    written = _call(
        "set_clip_notes",
        {"track_index": track_index, "clip_index": clip_index, "notes": updated},
    )
    return _json(
        {
            "humanized": len(updated),
            "timing_beats": timing,
            "velocity": velocity,
            "seed": seed,
            "result": written,
        }
    )


def detect_clip_key(ctx: Context, track_index: int, clip_index: int, weight: str = "kk") -> str:
    """Detect the key and scale of one Session MIDI clip (Krumhansl-Kessler profiles).

    weight: "kk" counts every note equally, "duration" weights by note length.
    """
    if weight not in ("kk", "duration"):
        raise ValueError('weight must be "kk" or "duration"')
    result = _call("get_clip_notes", {"track_index": track_index, "clip_index": clip_index})
    notes = _notes_of(result)
    histogram = _histogram_from_notes(notes, weight)
    detection = _best_key(histogram, weight)
    detection["notes"] = len(notes)
    return _json(detection)


def detect_track_key(ctx: Context, track_index: int, weight: str = "kk") -> str:
    """Detect the key of a whole track by pooling the notes of every MIDI clip on it.

    weight: "kk" counts every note equally, "duration" weights by note length.
    """
    if weight not in ("kk", "duration"):
        raise ValueError('weight must be "kk" or "duration"')

    track = _call("get_track_info", {"track_index": track_index})
    slots = track.get("clip_slots", []) if isinstance(track, dict) else []

    # get_track_info returns slots as {"index", "has_clip", "clip": {name, length, ...}}.
    histogram = [0.0] * 12
    notes_seen = 0
    clips_read = 0
    clip_names: List[str] = []
    for slot in slots:
        if not isinstance(slot, dict) or not slot.get("has_clip"):
            continue
        index = slot.get("index")
        if not isinstance(index, int):
            continue
        try:
            result = _call("get_clip_notes", {"track_index": track_index, "clip_index": index})
        except Exception:  # audio clips and empty slots simply contribute nothing
            continue
        notes = _notes_of(result)
        if not notes:
            continue
        clips_read += 1
        notes_seen += len(notes)
        info = slot.get("clip") if isinstance(slot.get("clip"), dict) else {}
        clip_names.append(str(info.get("name", f"slot {index}")))
        for i, value in enumerate(_histogram_from_notes(notes, weight)):
            histogram[i] += value

    detection = _best_key(histogram, weight)
    detection.update({"clips_read": clips_read, "notes": notes_seen, "clips": clip_names})
    return _json(detection)


# ============================================================================
# Enableton tools served by existing bridge commands under different names
# ============================================================================

def back_to_arranger(ctx: Context) -> str:
    """Leave an active Session clip and return playback to the arrangement."""
    return _json(_call("trigger_back_to_arrangement"))


def get_grooves(ctx: Context) -> str:
    """List the grooves available in the current set's groove pool."""
    return _json(_call("get_groove_pool"))


def get_track_meters(ctx: Context, track_index: int) -> str:
    """Read a track's output meter levels (left and right)."""
    return _json(_call("get_track_output_meter", {"track_index": track_index}))


def get_drum_pads(ctx: Context, track_index: int, device_index: int) -> str:
    """List the pads of a Drum Rack on a track, with their notes and sample names."""
    return _json(
        _call("get_drum_rack_pads", {"track_index": track_index, "device_index": device_index})
    )


def get_group_info(ctx: Context, track_index: int) -> str:
    """Report whether a track is inside a group.

    This bridge only exposes the grouped flag; Enableton's version also returns the
    group's name and member list.
    """
    return _json(_call("get_track_is_grouped", {"track_index": track_index}))


def get_track_routing(ctx: Context, track_index: int) -> str:
    """Read a track's input and output routing in one call."""
    return _json(
        {
            "track_index": track_index,
            "input": _call("get_track_input_routing", {"track_index": track_index}),
            "output": _call("get_track_output_routing", {"track_index": track_index}),
        }
    )


def clear_automation(ctx: Context, track_index: int, clip_index: int, device_index: int, parameter: str) -> str:
    """Clear one parameter's envelope from a clip.

    device_index is accepted for signature compatibility; this bridge identifies the
    parameter by name, so `parameter` must match the name Live shows.
    """
    if not parameter:
        raise ValueError("parameter must be a parameter name")
    return _json(
        _call(
            "clear_clip_automation",
            {
                "track_index": track_index,
                "clip_index": clip_index,
                "parameter_name": parameter,
            },
        )
    )


def jump_by(ctx: Context, beats: float) -> str:
    """Scrub the playhead by a number of beats (negative moves backwards)."""
    return _json(_call("scrub_by", {"delta": beats}))


def jump_to_cue(ctx: Context, direction: str = "") -> str:
    """Jump to the next or previous cue point.

    direction: "next"/"forward" or "prev"/"previous"/"back". A numeric string or int
    jumps to that cue point index instead, when the bridge supports indexed cues.
    """
    value = str(direction or "").strip().lower()
    if value in ("next", "forward"):
        return _json(_call("jump_to_next_cue"))
    if value in ("prev", "previous", "back", "backward"):
        return _json(_call("jump_to_prev_cue"))
    if value.isdigit():
        return _json(_call("jump_to_cue_point", {"index": int(value)}))
    raise ValueError('direction must be "next", "prev" or a cue point index')


def get_scale_info(ctx: Context) -> str:
    """Read the song's root note and scale."""
    return _json(_call("get_song_scale"))


def get_session_snapshot(ctx: Context) -> str:
    """One read of transport, track mixer state, return names, and scene names.

    Older Remote Scripts have no get_session_snapshot command. Those fall back
    to session info plus the track name list.
    """
    try:
        return _json(_call("get_session_snapshot"))
    except Exception as exc:
        if "Unknown command" not in str(exc):
            raise
    session = _call("get_session_info")
    names = _call("get_all_track_names")
    return _json({"session": session, "tracks": names})


def edit_notes(
    ctx: Context,
    track_index: int,
    clip_index: int,
    add: List[Dict[str, Any]] | None = None,
    remove: List[Dict[str, Any]] | None = None,
) -> str:
    """Add and/or remove individual notes without rewriting the whole clip.

    add: notes as {pitch, start_time, duration, velocity, mute}.
    remove: notes to match by pitch and start_time (within a 32nd of a beat).
    Untouched notes keep their exact timing.
    """
    add = add or []
    remove = remove or []
    if not add and not remove:
        raise ValueError("pass at least one note in add or remove")

    existing = _notes_of(
        _call("get_clip_notes", {"track_index": track_index, "clip_index": clip_index})
    )
    kept: List[Dict[str, Any]] = []
    removed = 0
    for note in existing:
        matched = False
        for target in remove:
            if int(target.get("pitch", -1)) != int(note.get("pitch", -2)):
                continue
            if abs(float(target.get("start_time", -1.0)) - float(note.get("start_time", -2.0))) <= 0.03125:
                matched = True
                break
        if matched:
            removed += 1
            continue
        kept.append(note)

    for note in add:
        kept.append(
            {
                "pitch": int(note.get("pitch", 60)),
                "start_time": float(note.get("start_time", 0.0)),
                "duration": float(note.get("duration", 0.25)),
                "velocity": int(note.get("velocity", 100)),
                "mute": bool(note.get("mute", False)),
            }
        )

    written = _call(
        "set_clip_notes",
        {"track_index": track_index, "clip_index": clip_index, "notes": kept},
    )
    return _json({"added": len(add), "removed": removed, "notes": len(kept), "result": written})


# ============================================================================
# Registration
# ============================================================================

REGISTERED_TOOLS = (
    continue_playing,
    stop_all_clips,
    tap_tempo,
    set_swing_amount,
    set_groove_amount,
    set_crossfader,
    set_clip_trigger_quantization,
    set_session_automation_record,
    set_arrangement_overdub,
    re_enable_automation,
    set_arrangement_time,
    create_return_track,
    delete_return_track,
    get_clip_info,
    quantize_clip,
    humanize_clip,
    detect_clip_key,
    detect_track_key,
    back_to_arranger,
    get_grooves,
    get_track_meters,
    get_drum_pads,
    get_group_info,
    get_track_routing,
    clear_automation,
    jump_by,
    jump_to_cue,
    get_scale_info,
    get_session_snapshot,
    edit_notes,
)


# Behaviour hints so clients can tell reads from writes and flag destructive calls.
TOOL_HINTS = {
    "continue_playing": WRITE,
    "stop_all_clips": WRITE,
    "tap_tempo": WRITE,
    "set_swing_amount": WRITE_IDEMPOTENT,
    "set_groove_amount": WRITE_IDEMPOTENT,
    "set_crossfader": WRITE_IDEMPOTENT,
    "set_clip_trigger_quantization": WRITE_IDEMPOTENT,
    "set_session_automation_record": WRITE_IDEMPOTENT,
    "set_arrangement_overdub": WRITE_IDEMPOTENT,
    "re_enable_automation": WRITE,
    "set_arrangement_time": WRITE_IDEMPOTENT,
    "create_return_track": WRITE,
    "delete_return_track": DESTRUCTIVE,
    "get_clip_info": READ_ONLY,
    "quantize_clip": WRITE,
    "humanize_clip": WRITE,
    "detect_clip_key": READ_ONLY,
    "detect_track_key": READ_ONLY,
    "back_to_arranger": WRITE,
    "get_grooves": READ_ONLY,
    "get_track_meters": READ_ONLY,
    "get_drum_pads": READ_ONLY,
    "get_group_info": READ_ONLY,
    "get_track_routing": READ_ONLY,
    "clear_automation": DESTRUCTIVE,
    "jump_by": WRITE,
    "jump_to_cue": WRITE_IDEMPOTENT,
    "get_scale_info": READ_ONLY,
    "get_session_snapshot": READ_ONLY,
    "edit_notes": DESTRUCTIVE,
}


def register_enableton_tools(mcp) -> int:
    """Register every ported tool on the given FastMCP instance. Returns the count."""
    for function in REGISTERED_TOOLS:
        mcp.tool(annotations=TOOL_HINTS.get(function.__name__))(function)
    return len(REGISTERED_TOOLS)
