# Gap commands from Enableton's catalogue that this Remote Script did not implement.
#
# Each name is a bridge command: {"type": "<name>", "params": {...}} in,
# a result dict out. Reads run on the caller. Writes are scheduled onto
# Live's main thread by AbletonMCP._dispatch_gap_command.
#
# Kept compatible with the Python that ships inside Live 10 (2.7) and
# Live 11+ (3.x). Live 11+ APIs are probed with hasattr and raise a clear
# error on older builds.

from __future__ import absolute_import

import os


AUDIO_FILE_EXTS = (".wav", ".aif", ".aiff", ".flac", ".mp3", ".ogg")
MAX_BATCH = 32

# Command names that only read Live. Everything else in HANDLERS writes.
READ_COMMANDS = set([
    "get_arrangement_clips",
    "get_device_routing",
    "get_master_device_parameters",
    "get_master_meters",
    "get_return_device_parameters",
    "get_session_snapshot",
])


def _require(params, key):
    if key not in params or params.get(key) is None:
        raise ValueError("Missing parameter: " + key)
    return params[key]


def _track(surface, index):
    tracks = list(surface._song.tracks)
    index = int(index)
    if index < 0 or index >= len(tracks):
        last = len(tracks) - 1
        raise IndexError("Track index {0} out of range (0-{1})".format(index, last))
    return tracks[index]


def _return_track(surface, index):
    tracks = list(surface._song.return_tracks)
    index = int(index)
    if index < 0 or index >= len(tracks):
        last = len(tracks) - 1
        raise IndexError("Return track index {0} out of range (0-{1})".format(index, last))
    return tracks[index]


def _slot(surface, track_index, clip_index):
    track = _track(surface, track_index)
    slots = list(track.clip_slots)
    clip_index = int(clip_index)
    if clip_index < 0 or clip_index >= len(slots):
        last = len(slots) - 1
        raise IndexError("Clip index {0} out of range (0-{1})".format(clip_index, last))
    return track, slots[clip_index]


def _clip(surface, track_index, clip_index):
    _track_obj, slot = _slot(surface, track_index, clip_index)
    if not slot.has_clip:
        raise ValueError("No clip in slot")
    return slot.clip


def _device_on(track, params):
    devices = list(track.devices)
    device_index = int(params.get("device_index", 0))
    if device_index < 0 or device_index >= len(devices):
        last = len(devices) - 1
        raise IndexError("Device index {0} out of range (0-{1})".format(device_index, last))
    device = devices[device_index]
    if "chain_index" in params and getattr(device, "can_have_chains", False):
        chains = list(device.chains)
        chain_index = int(params["chain_index"])
        if chain_index < 0 or chain_index >= len(chains):
            raise IndexError("Chain index {0} out of range".format(chain_index))
        chain = chains[chain_index]
        nested = list(chain.devices)
        nested_index = int(params.get("chain_device_index", 0))
        if nested_index < 0 or nested_index >= len(nested):
            raise IndexError("Chain device index {0} out of range".format(nested_index))
        device = nested[nested_index]
    return device


def _routing_view(value):
    if value is None:
        return None
    if isinstance(value, dict):
        return {
            "display_name": value.get("display_name"),
            "identifier": value.get("identifier"),
        }
    return {
        "display_name": getattr(value, "display_name", None),
        "identifier": getattr(value, "identifier", None),
    }


def _routing_list(values):
    if not values:
        return []
    return [_routing_view(item) for item in list(values)]


def _routing_label(item):
    view = _routing_view(item) or {}
    return (view.get("display_name") or "", view.get("identifier") or "")


def _pick_routing(available, wanted):
    items = list(available or [])
    if isinstance(wanted, int) or (isinstance(wanted, str) and wanted.isdigit()):
        index = int(wanted)
        if index < 0 or index >= len(items):
            raise IndexError("Routing index {0} out of range".format(index))
        return items[index]
    needle = str(wanted).strip().lower()
    for item in items:
        display_name, identifier = _routing_label(item)
        if needle in (str(display_name).lower(), str(identifier).lower()):
            return item
    names = [str(_routing_label(item)[0]) for item in items]
    raise ValueError("Routing '{0}' not available. Choices: {1}".format(wanted, ", ".join(names)))


def _param_info(param, index):
    info = {
        "index": index,
        "name": param.name,
        "value": param.value,
        "min": param.min,
        "max": param.max,
        "is_enabled": bool(getattr(param, "is_enabled", True)),
        "is_quantized": bool(getattr(param, "is_quantized", False)),
    }
    if info["is_quantized"] and hasattr(param, "value_items"):
        info["value_items"] = list(param.value_items)
    return info


def _device_parameters(device, track_label):
    parameters = []
    for index, param in enumerate(list(device.parameters)):
        parameters.append(_param_info(param, index))
    return {
        "track": track_label,
        "device_name": device.name,
        "device_class": getattr(device, "class_name", ""),
        "parameter_count": len(parameters),
        "parameters": parameters,
    }


def _meters(track):
    result = {"name": getattr(track, "name", "")}
    for key in (
        "output_meter_left",
        "output_meter_right",
        "output_meter_level",
        "input_meter_left",
        "input_meter_right",
        "input_meter_level",
    ):
        if hasattr(track, key):
            try:
                result[key] = getattr(track, key)
            except Exception:
                pass
    return result


def _clip_summary(clip, index):
    return {
        "index": index,
        "name": clip.name,
        "start_time": getattr(clip, "start_time", None),
        "end_time": getattr(clip, "end_time", None),
        "length": getattr(clip, "length", None),
        "color": getattr(clip, "color", None),
        "muted": bool(getattr(clip, "muted", False)),
        "is_midi_clip": bool(getattr(clip, "is_midi_clip", False)),
        "is_audio_clip": bool(getattr(clip, "is_audio_clip", False)),
    }


def _check_audio_file(file_path):
    if not file_path or not isinstance(file_path, str):
        raise ValueError("file_path is required")
    if not os.path.isabs(file_path):
        raise ValueError("file_path must be an absolute path")
    if not os.path.isfile(file_path):
        raise ValueError("Audio file not found: " + file_path)
    ext = os.path.splitext(file_path)[1].lower()
    if ext not in AUDIO_FILE_EXTS:
        raise ValueError("Unsupported audio extension '{0}'".format(ext))
    return file_path


def _find_parameter(track, params):
    if "device_index" in params and ("parameter_index" in params or "parameter" in params):
        device = _device_on(track, params)
        if "parameter_index" in params:
            parameters = list(device.parameters)
            index = int(params["parameter_index"])
            if index < 0 or index >= len(parameters):
                raise IndexError("Parameter index {0} out of range".format(index))
            return parameters[index]
        name = str(params.get("parameter", params.get("parameter_name", ""))).lower()
        for param in device.parameters:
            if param.name.lower() == name:
                return param
        raise ValueError("Parameter not found: " + name)
    name = str(params.get("parameter_name", params.get("parameter", ""))).lower()
    if not name:
        raise ValueError("Pass parameter_name, or device_index plus parameter_index")
    for device in track.devices:
        for param in device.parameters:
            if param.name.lower() == name:
                return param
    raise ValueError("Parameter not found: " + name)


def _find_simpler(track, params):
    if "device_index" in params:
        device = _device_on(track, params)
        class_name = getattr(device, "class_name", "")
        if class_name not in ("OriginalSimpler", "Simpler"):
            raise ValueError("Device {0} is not a Simpler".format(device.name))
        return device
    for device in track.devices:
        if getattr(device, "class_name", "") in ("OriginalSimpler", "Simpler"):
            return device
    raise ValueError("No Simpler on this track")


def _load_browser_uri(surface, track, uri):
    app = surface.application()
    item = surface._find_browser_item_by_uri(app.browser, uri)
    if not item:
        raise ValueError("Browser item with URI '{0}' not found".format(uri))
    surface._song.view.selected_track = track
    app.browser.load_item(item)
    return item


def _begin_undo(song):
    begin = getattr(song, "begin_undo_step", None)
    if not callable(begin):
        return False
    try:
        begin()
    except TypeError:
        begin("AbletonMCP batch")
    return True


def _end_undo(song):
    end = getattr(song, "end_undo_step", None)
    if callable(end):
        end()


# --------------------------------------------------------------------------
# Reads
# --------------------------------------------------------------------------

def get_arrangement_clips(surface, params):
    """List Arrangement clips on a track, in Live's order."""
    track = _track(surface, _require(params, "track_index"))
    if not hasattr(track, "arrangement_clips"):
        raise ValueError("Arrangement clips are not available in this Live version")
    clips = []
    for index, clip in enumerate(list(track.arrangement_clips)):
        clips.append(_clip_summary(clip, index))
    return {"track_index": int(params["track_index"]), "clip_count": len(clips), "clips": clips}


def get_device_routing(surface, params):
    """Read device routing. Max devices expose buses; Compressor exposes sidechain."""
    track = _track(surface, _require(params, "track_index"))
    device = _device_on(track, params)
    buses = {}
    for bus_name in ("audio_inputs", "audio_outputs", "midi_inputs", "midi_outputs"):
        if not hasattr(device, bus_name):
            continue
        described = []
        for index, bus in enumerate(list(getattr(device, bus_name))):
            described.append({
                "index": index,
                "routing_type": _routing_view(getattr(bus, "routing_type", None)),
                "routing_channel": _routing_view(getattr(bus, "routing_channel", None)),
                "available_routing_types": _routing_list(getattr(bus, "available_routing_types", None)),
                "available_routing_channels": _routing_list(getattr(bus, "available_routing_channels", None)),
            })
        buses[bus_name] = described
    sidechain = None
    if hasattr(device, "input_routing_type"):
        sidechain = {
            "input_routing_type": _routing_view(device.input_routing_type),
            "input_routing_channel": _routing_view(getattr(device, "input_routing_channel", None)),
            "available_input_routing_types": _routing_list(getattr(device, "available_input_routing_types", None)),
            "available_input_routing_channels": _routing_list(getattr(device, "available_input_routing_channels", None)),
        }
    return {
        "track_index": int(params["track_index"]),
        "device_index": int(params.get("device_index", 0)),
        "device_name": device.name,
        "device_class": getattr(device, "class_name", ""),
        "buses": buses,
        "sidechain": sidechain,
    }


def get_master_device_parameters(surface, params):
    """Parameters of a device on the master track. Same shape as get_device_parameters."""
    master = surface._song.master_track
    device = _device_on(master, params)
    result = _device_parameters(device, "master")
    result["device_index"] = int(params.get("device_index", 0))
    return result


def get_master_meters(surface, params):
    """Master input and output meters. Values are 0.0-1.0 and move only while audio runs."""
    return _meters(surface._song.master_track)


def get_return_device_parameters(surface, params):
    """Parameters of a device on a return track."""
    track = _return_track(surface, _require(params, "return_index"))
    device = _device_on(track, params)
    result = _device_parameters(device, track.name)
    result["return_index"] = int(params["return_index"])
    result["device_index"] = int(params.get("device_index", 0))
    return result


def get_session_snapshot(surface, params):
    """Compact session picture: transport, tracks, returns, and scene names."""
    song = surface._song
    tracks = []
    for index, track in enumerate(list(song.tracks)):
        volume = None
        pan = None
        try:
            volume = track.mixer_device.volume.value
            pan = track.mixer_device.panning.value
        except Exception:
            pass
        playing_slot = None
        try:
            playing_slot = track.playing_slot_index
        except Exception:
            pass
        tracks.append({
            "index": index,
            "name": track.name,
            "mute": bool(getattr(track, "mute", False)),
            "solo": bool(getattr(track, "solo", False)),
            "volume": volume,
            "pan": pan,
            "playing_slot_index": playing_slot,
            "is_foldable": bool(getattr(track, "is_foldable", False)),
        })
    returns = []
    for index, track in enumerate(list(song.return_tracks)):
        returns.append({"index": index, "name": track.name})
    scenes = []
    for index, scene in enumerate(list(song.scenes)):
        scenes.append({"index": index, "name": scene.name})
    return {
        "tempo": song.tempo,
        "is_playing": bool(song.is_playing),
        "current_song_time": getattr(song, "current_song_time", None),
        "signature_numerator": song.signature_numerator,
        "signature_denominator": song.signature_denominator,
        "loop": bool(getattr(song, "loop", False)),
        "loop_start": getattr(song, "loop_start", None),
        "loop_length": getattr(song, "loop_length", None),
        "record_mode": bool(getattr(song, "record_mode", False)),
        "session_record": bool(getattr(song, "session_record", False)),
        "scale_name": getattr(song, "scale_name", None),
        "root_note": getattr(song, "root_note", None),
        "track_count": len(tracks),
        "tracks": tracks,
        "returns": returns,
        "scenes": scenes,
    }


# --------------------------------------------------------------------------
# Arrangement, clips, take lanes
# --------------------------------------------------------------------------

def delete_arrangement_clip(surface, params):
    """Delete one Arrangement clip by arrangement_index or by start_time in beats."""
    track = _track(surface, _require(params, "track_index"))
    clips = list(getattr(track, "arrangement_clips", []) or [])
    if not clips:
        raise ValueError("Track has no arrangement clips")
    if "arrangement_index" in params:
        index = int(params["arrangement_index"])
        if index < 0 or index >= len(clips):
            raise IndexError("Arrangement clip index {0} out of range".format(index))
        clip = clips[index]
    elif "start_time" in params:
        target = float(params["start_time"])
        clip = None
        for candidate in clips:
            if abs(float(candidate.start_time) - target) < 0.001:
                clip = candidate
                break
        if clip is None:
            raise ValueError("No arrangement clip starts at {0}".format(target))
        index = clips.index(clip)
    else:
        raise ValueError("Pass arrangement_index or start_time")
    if not hasattr(track, "delete_clip"):
        raise ValueError("This Live version cannot delete arrangement clips")
    name = clip.name
    start_time = clip.start_time
    track.delete_clip(clip)
    return {
        "deleted": True,
        "track_index": int(params["track_index"]),
        "arrangement_index": index,
        "name": name,
        "start_time": start_time,
    }


def duplicate_clip_to(surface, params):
    """Duplicate a Session clip slot onto another slot. Overwrites the target slot."""
    _source_track, source = _slot(surface, _require(params, "track_index"), _require(params, "clip_index"))
    if not source.has_clip:
        raise ValueError("Source slot has no clip")
    _target_track, target = _slot(
        surface,
        _require(params, "target_track_index"),
        _require(params, "target_clip_index"),
    )
    if not hasattr(source, "duplicate_clip_to"):
        raise ValueError("duplicate_clip_to is not available in this Live version")
    source.duplicate_clip_to(target)
    return {
        "duplicated": True,
        "track_index": int(params["track_index"]),
        "clip_index": int(params["clip_index"]),
        "target_track_index": int(params["target_track_index"]),
        "target_clip_index": int(params["target_clip_index"]),
        "name": target.clip.name if target.has_clip else None,
    }


def duplicate_session_clip_to_arrangement(surface, params):
    """Copy a Session clip onto the Arrangement at destination_time beats."""
    track, slot = _slot(surface, _require(params, "track_index"), _require(params, "clip_index"))
    if not slot.has_clip:
        raise ValueError("Source slot has no clip")
    destination_time = float(_require(params, "destination_time"))
    if not hasattr(track, "duplicate_clip_to_arrangement"):
        raise ValueError("duplicate_clip_to_arrangement is not available in this Live version")
    before = len(list(getattr(track, "arrangement_clips", []) or []))
    track.duplicate_clip_to_arrangement(slot.clip, destination_time)
    after = list(getattr(track, "arrangement_clips", []) or [])
    created = None
    for clip in after:
        try:
            if abs(float(clip.start_time) - destination_time) < 0.001:
                created = _clip_summary(clip, after.index(clip))
                break
        except Exception:
            continue
    return {
        "duplicated": True,
        "track_index": int(params["track_index"]),
        "clip_index": int(params["clip_index"]),
        "destination_time": destination_time,
        "arrangement_clip_count": len(after),
        "grew": len(after) > before,
        "clip": created,
    }


def create_audio_clip(surface, params):
    """Create an audio clip from an absolute file path.

    Session: track_index, clip_index, file_path. The slot must be empty and the
    track must be an audio track.
    Arrangement: track_index, file_path, position (beats). Pass arrangement=true
    when both clip_index and position are present.
    """
    file_path = _check_audio_file(_require(params, "file_path"))
    track = _track(surface, _require(params, "track_index"))
    if getattr(track, "is_frozen", False):
        raise ValueError("Track is frozen")
    if hasattr(track, "has_audio_input") and not track.has_audio_input:
        raise ValueError("Track is not an audio track")
    arrangement = bool(params.get("arrangement", False)) or (
        "position" in params and "clip_index" not in params
    )
    if arrangement:
        if not hasattr(track, "create_audio_clip"):
            raise ValueError("Arrangement audio clips are not available in this Live version")
        position = float(params.get("position", params.get("time", 0.0)))
        track.create_audio_clip(file_path, position)
        return {
            "created": True,
            "where": "arrangement",
            "track_index": int(params["track_index"]),
            "position": position,
            "file_path": file_path,
        }
    _track_obj, slot = _slot(surface, params["track_index"], _require(params, "clip_index"))
    if slot.has_clip:
        raise ValueError("Clip slot is not empty")
    if hasattr(track, "has_audio_input") and not track.has_audio_input:
        raise ValueError("Track is not an audio track")
    if not hasattr(slot, "create_audio_clip"):
        raise ValueError("create_audio_clip is not available on this clip slot")
    slot.create_audio_clip(file_path)
    clip = slot.clip
    if params.get("name"):
        clip.name = str(params["name"])
    return {
        "created": True,
        "where": "session",
        "track_index": int(params["track_index"]),
        "clip_index": int(params["clip_index"]),
        "file_path": file_path,
        "name": clip.name,
        "sample_rate": getattr(clip, "sample_rate", None),
        "sample_length": getattr(clip, "sample_length", None),
        "warping": bool(getattr(clip, "warping", False)),
    }


def set_clip_audio(surface, params):
    """Replace a Session slot's audio file, then apply optional clip audio properties.

    file_path deletes the existing clip and creates a new one from that file.
    gain, pitch_coarse, pitch_fine, warping, warp_mode, and ram_mode are applied
    when present, with or without a new file.
    """
    track_index = _require(params, "track_index")
    clip_index = _require(params, "clip_index")
    track, slot = _slot(surface, track_index, clip_index)
    replaced = False
    if params.get("file_path"):
        file_path = _check_audio_file(params["file_path"])
        if getattr(track, "is_frozen", False):
            raise ValueError("Track is frozen")
        if hasattr(track, "has_audio_input") and not track.has_audio_input:
            raise ValueError("Track is not an audio track")
        if slot.has_clip and hasattr(slot, "delete_clip"):
            slot.delete_clip()
        if not hasattr(slot, "create_audio_clip"):
            raise ValueError("create_audio_clip is not available on this clip slot")
        slot.create_audio_clip(file_path)
        replaced = True
    if not slot.has_clip:
        raise ValueError("No clip in slot")
    clip = slot.clip
    applied = []
    if "gain" in params:
        clip.gain = float(params["gain"])
        applied.append("gain")
    if "pitch_coarse" in params:
        clip.pitch_coarse = int(params["pitch_coarse"])
        applied.append("pitch_coarse")
    if "pitch_fine" in params:
        clip.pitch_fine = float(params["pitch_fine"])
        applied.append("pitch_fine")
    if "warping" in params:
        clip.warping = bool(params["warping"])
        applied.append("warping")
    if "warp_mode" in params:
        clip.warp_mode = int(params["warp_mode"])
        applied.append("warp_mode")
    if "ram_mode" in params:
        clip.ram_mode = bool(params["ram_mode"])
        applied.append("ram_mode")
    if "name" in params:
        clip.name = str(params["name"])
        applied.append("name")
    if not replaced and not applied:
        raise ValueError("Pass file_path or at least one audio property")
    return {
        "track_index": int(track_index),
        "clip_index": int(clip_index),
        "replaced": replaced,
        "applied": applied,
        "name": clip.name,
    }


def create_take_lane(surface, params):
    """Create an Arrangement take lane on a track. Live 11+."""
    track = _track(surface, _require(params, "track_index"))
    if not hasattr(track, "create_take_lane"):
        raise ValueError("Take lanes are not available in this Live version")
    track.create_take_lane()
    lanes = list(getattr(track, "take_lanes", []) or [])
    name = None
    if params.get("name") and lanes:
        lanes[-1].name = str(params["name"])
        name = lanes[-1].name
    return {
        "track_index": int(params["track_index"]),
        "take_lane_count": len(lanes),
        "name": name,
    }


def clip_op(surface, params):
    """One clip operation that has no command of its own.

    operation is one of: crop, duplicate_loop, duplicate_region, quantize,
    select_all_notes, deselect_all_notes, mute, name, color, looping, gain,
    pitch, warp, markers, ram_mode.
    """
    operation = str(_require(params, "operation")).strip().lower()
    clip = _clip(surface, _require(params, "track_index"), _require(params, "clip_index"))
    if operation == "crop":
        clip.crop()
    elif operation == "duplicate_loop":
        clip.duplicate_loop()
    elif operation == "duplicate_region":
        clip.duplicate_region(
            float(_require(params, "region_start")),
            float(_require(params, "region_length")),
            float(_require(params, "destination_time")),
            int(params.get("pitch", -1)),
            int(params.get("transposition_amount", 0)),
        )
    elif operation == "quantize":
        clip.quantize(int(_require(params, "grid")), float(params.get("amount", 1.0)))
    elif operation == "select_all_notes":
        clip.select_all_notes()
    elif operation == "deselect_all_notes":
        clip.deselect_all_notes()
    elif operation == "mute":
        clip.muted = bool(_require(params, "muted"))
    elif operation == "name":
        clip.name = str(_require(params, "name"))
    elif operation == "color":
        clip.color = int(_require(params, "color"))
    elif operation == "looping":
        if "looping" in params:
            clip.looping = bool(params["looping"])
        if "loop_start" in params:
            clip.loop_start = float(params["loop_start"])
        if "loop_end" in params:
            clip.loop_end = float(params["loop_end"])
    elif operation == "gain":
        clip.gain = float(_require(params, "gain"))
    elif operation == "pitch":
        if "pitch_coarse" in params:
            clip.pitch_coarse = int(params["pitch_coarse"])
        if "pitch_fine" in params:
            clip.pitch_fine = float(params["pitch_fine"])
    elif operation == "warp":
        if "warping" in params:
            clip.warping = bool(params["warping"])
        if "warp_mode" in params:
            clip.warp_mode = int(params["warp_mode"])
    elif operation == "markers":
        if "start_marker" in params:
            clip.start_marker = float(params["start_marker"])
        if "end_marker" in params:
            clip.end_marker = float(params["end_marker"])
    elif operation == "ram_mode":
        clip.ram_mode = bool(_require(params, "ram_mode"))
    else:
        raise ValueError("Unknown clip operation: " + operation)
    return {
        "operation": operation,
        "track_index": int(params["track_index"]),
        "clip_index": int(params["clip_index"]),
        "name": clip.name,
        "length": getattr(clip, "length", None),
    }


def set_clip_groove(surface, params):
    """Assign a groove-pool groove to a clip, by name or index. Live 11+."""
    clip = _clip(surface, _require(params, "track_index"), _require(params, "clip_index"))
    pool = getattr(surface._song, "groove_pool", None)
    if pool is None:
        raise ValueError("Groove pool is not available in this Live version")
    grooves = list(pool.grooves)
    if "groove_index" in params:
        index = int(params["groove_index"])
        if index < 0 or index >= len(grooves):
            raise IndexError("Groove index {0} out of range".format(index))
        groove = grooves[index]
    else:
        name = str(_require(params, "groove_name")).strip().lower()
        groove = None
        for candidate in grooves:
            if str(candidate.name).strip().lower() == name:
                groove = candidate
                break
        if groove is None:
            raise ValueError("Groove not found: " + name)
    clip.groove = groove
    return {"groove_name": groove.name, "has_groove": bool(getattr(clip, "has_groove", True))}


def set_clip_signature(surface, params):
    """Set a clip's time signature numerator and denominator."""
    clip = _clip(surface, _require(params, "track_index"), _require(params, "clip_index"))
    numerator = int(_require(params, "numerator"))
    denominator = int(_require(params, "denominator"))
    if numerator < 1 or denominator < 1:
        raise ValueError("Time signature parts must be >= 1")
    clip.signature_numerator = numerator
    clip.signature_denominator = denominator
    return {
        "numerator": clip.signature_numerator,
        "denominator": clip.signature_denominator,
    }


def write_automation(surface, params):
    """Write clip automation breakpoints for one device parameter.

    points is a list of {time, value} in beats and raw parameter units.
    clear defaults to true and wipes the envelope before inserting.
    """
    track = _track(surface, _require(params, "track_index"))
    clip = _clip(surface, params["track_index"], _require(params, "clip_index"))
    param = _find_parameter(track, params)
    points = params.get("points", [])
    if not isinstance(points, list):
        raise ValueError("points must be a list of {time, value}")
    if not hasattr(clip, "create_automation_envelope"):
        raise ValueError("Automation envelopes are not supported in this Live version")
    envelope = clip.create_automation_envelope(param)
    cleared = False
    if params.get("clear", True) and hasattr(envelope, "clear"):
        envelope.clear()
        cleared = True
    written = 0
    for point in points:
        if not isinstance(point, dict):
            raise ValueError("Each automation point must be an object")
        time_value = float(point.get("time", 0.0))
        value = float(point.get("value", param.value))
        value = max(param.min, min(param.max, value))
        if hasattr(envelope, "insert_value"):
            envelope.insert_value(time_value, value)
            written += 1
        else:
            raise ValueError("This Live version cannot insert automation points")
    return {
        "parameter_name": param.name,
        "points_written": written,
        "cleared": cleared,
    }


# --------------------------------------------------------------------------
# Devices, racks, simpler, drums
# --------------------------------------------------------------------------

def _insert_or_load(surface, track, params):
    device_name = params.get("device_name")
    if device_name:
        if not hasattr(track, "insert_device"):
            raise ValueError("insert_device needs Live 12.3 or newer. Pass item_uri to load from the browser.")
        before = len(list(track.devices))
        if "index" in params and params["index"] is not None:
            track.insert_device(str(device_name), int(params["index"]))
        else:
            track.insert_device(str(device_name))
        after = len(list(track.devices))
        return {
            "loaded": True,
            "method": "insert_device",
            "device_name": str(device_name),
            "track_name": track.name,
            "device_count": after,
            "grew": after > before,
        }
    uri = params.get("item_uri") or params.get("uri")
    if not uri:
        raise ValueError("Pass device_name (Live 12.3+ native device) or item_uri")
    item = _load_browser_uri(surface, track, uri)
    return {
        "loaded": True,
        "method": "browser",
        "item_name": item.name,
        "uri": uri,
        "track_name": track.name,
    }


def load_device_to_master(surface, params):
    """Load a native device or a browser item onto the master track."""
    return _insert_or_load(surface, surface._song.master_track, params)


def load_device_to_return(surface, params):
    """Load a native device or a browser item onto a return track."""
    track = _return_track(surface, _require(params, "return_index"))
    result = _insert_or_load(surface, track, params)
    result["return_index"] = int(params["return_index"])
    return result


def set_device_enabled(surface, params):
    """Turn a device on or off via its Device On parameter."""
    track = _track(surface, _require(params, "track_index"))
    device = _device_on(track, params)
    enabled = bool(params.get("enabled", True))
    target = None
    for param in device.parameters:
        if str(param.name).strip().lower() in ("device on", "on"):
            target = param
            break
    if target is None:
        raise ValueError("Device '{0}' has no on/off parameter".format(device.name))
    target.value = 1 if enabled else 0
    return {"device_name": device.name, "enabled": enabled, "parameter": target.name, "value": target.value}


def set_device_routing(surface, params):
    """Set a device bus or a Compressor sidechain route by name or index.

    bus is audio_inputs (default), audio_outputs, midi_inputs, or midi_outputs.
    bus_index selects which bus. routing_type and routing_channel match
    display_name, identifier, or a list index.
    Sidechain uses input_type and input_channel on devices that have them.
    """
    track = _track(surface, _require(params, "track_index"))
    device = _device_on(track, params)
    changed = []
    if "input_type" in params or "input_channel" in params:
        if not hasattr(device, "input_routing_type"):
            raise ValueError("Device has no sidechain input routing")
        if "input_type" in params:
            device.input_routing_type = _pick_routing(device.available_input_routing_types, params["input_type"])
            changed.append("input_type")
        if "input_channel" in params:
            device.input_routing_channel = _pick_routing(device.available_input_routing_channels, params["input_channel"])
            changed.append("input_channel")
    bus_name = str(params.get("bus", "audio_inputs"))
    if "routing_type" in params or "routing_channel" in params:
        if not hasattr(device, bus_name):
            raise ValueError("Device has no {0}".format(bus_name))
        buses = list(getattr(device, bus_name))
        bus_index = int(params.get("bus_index", 0))
        if bus_index < 0 or bus_index >= len(buses):
            raise IndexError("Bus index {0} out of range".format(bus_index))
        bus = buses[bus_index]
        if "routing_type" in params:
            bus.routing_type = _pick_routing(bus.available_routing_types, params["routing_type"])
            changed.append("routing_type")
        if "routing_channel" in params:
            bus.routing_channel = _pick_routing(bus.available_routing_channels, params["routing_channel"])
            changed.append("routing_channel")
    if not changed:
        raise ValueError("Pass routing_type, routing_channel, input_type, or input_channel")
    return {"device_name": device.name, "changed": changed}


def rack_variation(surface, params):
    """Store, select, recall, or delete a Rack macro variation. Live 11+.

    action is store, select, recall, recall_last, or delete.
    index is the variation index for select, recall, and delete.
    """
    track = _track(surface, _require(params, "track_index"))
    device = _device_on(track, params)
    if not getattr(device, "can_have_chains", False):
        raise ValueError("Device '{0}' is not a Rack".format(device.name))
    action = str(params.get("action", "store")).strip().lower()
    if "index" in params and action in ("select", "recall", "delete"):
        device.selected_variation_index = int(params["index"])
    if action == "store":
        device.store_variation()
    elif action == "select":
        if "index" not in params:
            raise ValueError("select requires index")
    elif action == "recall":
        device.recall_selected_variation()
    elif action in ("recall_last", "recall_last_used"):
        device.recall_last_used_variation()
    elif action == "delete":
        device.delete_selected_variation()
    else:
        raise ValueError("Unknown rack variation action: " + action)
    return {
        "action": action,
        "device_name": device.name,
        "variation_count": getattr(device, "variation_count", None),
        "selected_variation_index": getattr(device, "selected_variation_index", None),
    }


def set_simpler_playback_mode(surface, params):
    """Set Simpler playback mode: 0 classic, 1 one-shot, 2 slicing. Names are accepted."""
    track = _track(surface, _require(params, "track_index"))
    simpler = _find_simpler(track, params)
    raw = params.get("mode", params.get("playback_mode"))
    if raw is None:
        raise ValueError("Pass mode")
    names = {"classic": 0, "one-shot": 1, "oneshot": 1, "one_shot": 1, "slicing": 2}
    if isinstance(raw, str) and raw.strip().lower() in names:
        mode = names[raw.strip().lower()]
    else:
        mode = int(raw)
    if mode not in (0, 1, 2):
        raise ValueError("playback mode must be 0, 1, or 2")
    simpler.playback_mode = mode
    return {"device_name": simpler.name, "playback_mode": simpler.playback_mode}


def replace_simpler_sample(surface, params):
    """Replace the sample in a Simpler.

    file_path is used when this Live build exposes a load method on Simpler or
    its sample. Otherwise pass item_uri and the browser loads that item onto
    the selected Simpler. A raw disk path cannot be assigned on builds where
    Sample.file_path is read-only.
    """
    track = _track(surface, _require(params, "track_index"))
    simpler = _find_simpler(track, params)
    file_path = params.get("file_path")
    if file_path:
        file_path = _check_audio_file(file_path)
        sample = getattr(simpler, "sample", None)
        for owner, method_name in (
            (simpler, "load_sample"),
            (simpler, "replace_sample"),
            (sample, "load_sample"),
            (sample, "replace_sample"),
        ):
            method = getattr(owner, method_name, None) if owner is not None else None
            if callable(method):
                method(file_path)
                return {"replaced": True, "method": method_name, "file_path": file_path}
        if sample is not None and hasattr(sample, "file_path"):
            try:
                sample.file_path = file_path
                return {"replaced": True, "method": "sample.file_path", "file_path": file_path}
            except Exception as exc:
                file_error = str(exc)
            else:
                file_error = ""
        else:
            file_error = "Sample.file_path is not settable"
        if not (params.get("item_uri") or params.get("uri")):
            raise ValueError(
                "This Live version cannot replace a Simpler sample from a file path ({0}). "
                "Pass item_uri for a browser sample.".format(file_error)
            )
    uri = params.get("item_uri") or params.get("uri")
    if not uri:
        raise ValueError("Pass file_path or item_uri")
    surface._song.view.selected_track = track
    if hasattr(surface._song.view, "select_device"):
        surface._song.view.select_device(simpler)
    item = _load_browser_uri(surface, track, uri)
    return {"replaced": True, "method": "browser", "item_name": item.name, "uri": uri}


def set_drum_pad(surface, params):
    """Set a Drum Rack pad's mute, solo, or chain name.

    pad_index is the MIDI note (0-127). DrumPad.name is read-only in the LOM,
    so name is written onto the pad's first chain.
    """
    track = _track(surface, _require(params, "track_index"))
    device = _device_on(track, params)
    if not getattr(device, "can_have_drum_pads", False):
        raise ValueError("Device '{0}' is not a Drum Rack".format(device.name))
    pad_index = int(_require(params, "pad_index"))
    pads = list(device.drum_pads)
    if pad_index < 0 or pad_index >= len(pads):
        raise IndexError("Pad index {0} out of range".format(pad_index))
    pad = pads[pad_index]
    changed = []
    if "mute" in params:
        pad.mute = bool(params["mute"])
        changed.append("mute")
    if "solo" in params:
        pad.solo = bool(params["solo"])
        changed.append("solo")
    if "name" in params:
        chains = list(getattr(pad, "chains", []) or [])
        if not chains:
            raise ValueError("Pad has no chain to rename")
        chains[0].name = str(params["name"])
        changed.append("name")
    if not changed:
        raise ValueError("Pass mute, solo, or name")
    return {
        "pad_index": pad_index,
        "note": getattr(pad, "note", pad_index),
        "mute": bool(pad.mute),
        "solo": bool(pad.solo),
        "name": pad.name,
        "changed": changed,
    }


# --------------------------------------------------------------------------
# Mixer, routing, fold, song
# --------------------------------------------------------------------------

def set_crossfade_assign(surface, params):
    """Set a track's crossfade assign. 0 or A, 1 or none, 2 or B."""
    track = _track(surface, _require(params, "track_index"))
    assign = _require(params, "assign")
    names = {"a": 0, "none": 1, "b": 2}
    if isinstance(assign, str):
        key = assign.strip().lower()
        if key not in names:
            raise ValueError("assign must be A, none, or B")
        assign = names[key]
    else:
        assign = int(assign)
    if assign not in (0, 1, 2):
        raise ValueError("assign must be 0 (A), 1 (none), or 2 (B)")
    track.mixer_device.crossfade_assign = assign
    return {"track_index": int(params["track_index"]), "crossfade_assign": assign}


def set_send(surface, params):
    """Set one send level on a track. value is clamped to the send's min and max."""
    track = _track(surface, _require(params, "track_index"))
    send_index = int(_require(params, "send_index"))
    sends = list(track.mixer_device.sends)
    if send_index < 0 or send_index >= len(sends):
        raise IndexError("Send index {0} out of range".format(send_index))
    send = sends[send_index]
    value = float(_require(params, "value"))
    value = max(send.min, min(send.max, value))
    send.value = value
    return {"track_index": int(params["track_index"]), "send_index": send_index, "value": send.value}


def set_fold_state(surface, params):
    """Fold or unfold a group track. Falls back to Arrangement collapse on other tracks.

    folded (bool) or fold_state (0 visible, 1 folded).
    """
    track = _track(surface, _require(params, "track_index"))
    if "fold_state" in params:
        state = 1 if int(params["fold_state"]) else 0
    elif "folded" in params:
        state = 1 if params["folded"] else 0
    else:
        raise ValueError("Pass folded or fold_state")
    if getattr(track, "is_foldable", False):
        track.fold_state = state
        return {"track_index": int(params["track_index"]), "fold_state": track.fold_state, "via": "group"}
    view = getattr(track, "view", None)
    if view is not None and hasattr(view, "is_collapsed"):
        view.is_collapsed = bool(state)
        return {"track_index": int(params["track_index"]), "is_collapsed": bool(view.is_collapsed), "via": "arrangement"}
    raise ValueError("Track cannot be folded")


def set_track_routing(surface, params):
    """Set track input/output routing type and channel by name, identifier, or index.

    Set the type before the channel. Keys: input_type, input_channel,
    output_type, output_channel.
    """
    track = _track(surface, _require(params, "track_index"))
    changed = []
    pairs = (
        ("input_type", "input_routing_type", "available_input_routing_types"),
        ("input_channel", "input_routing_channel", "available_input_routing_channels"),
        ("output_type", "output_routing_type", "available_output_routing_types"),
        ("output_channel", "output_routing_channel", "available_output_routing_channels"),
    )
    for key, attr, available_name in pairs:
        if key not in params:
            continue
        if not hasattr(track, available_name):
            raise ValueError("Track has no " + available_name)
        setattr(track, attr, _pick_routing(getattr(track, available_name), params[key]))
        changed.append(key)
    if not changed:
        raise ValueError("Pass input_type, input_channel, output_type, or output_channel")
    return {"track_index": int(params["track_index"]), "changed": changed}


def set_loop(surface, params):
    """Set the Arrangement loop. enabled/loop, start/loop_start, length/loop_length."""
    song = surface._song
    if "enabled" in params or "loop" in params:
        song.loop = bool(params["enabled"] if "enabled" in params else params["loop"])
    if "start" in params or "loop_start" in params:
        song.loop_start = float(params["start"] if "start" in params else params["loop_start"])
    if "length" in params or "loop_length" in params:
        song.loop_length = float(params["length"] if "length" in params else params["loop_length"])
    return {"loop": bool(song.loop), "loop_start": song.loop_start, "loop_length": song.loop_length}


def set_time_signature(surface, params):
    """Set the song time signature. Alias of the LOM signature numerator and denominator."""
    song = surface._song
    numerator = int(_require(params, "numerator"))
    denominator = int(_require(params, "denominator"))
    if numerator < 1 or denominator < 1:
        raise ValueError("Time signature parts must be >= 1")
    song.signature_numerator = numerator
    song.signature_denominator = denominator
    return {"numerator": song.signature_numerator, "denominator": song.signature_denominator}


def set_song_scale(surface, params):
    """Set scale name, root note (0-11), and scale mode highlighting."""
    song = surface._song
    if "scale_name" not in params and "root_note" not in params and "scale_mode" not in params:
        raise ValueError("Pass scale_name, root_note, or scale_mode")
    if "scale_name" in params:
        if not hasattr(song, "scale_name"):
            raise ValueError("scale_name is not available in this Live version")
        song.scale_name = str(params["scale_name"])
    if "root_note" in params:
        song.root_note = int(params["root_note"]) % 12
    if "scale_mode" in params and hasattr(song, "scale_mode"):
        song.scale_mode = bool(params["scale_mode"])
    return {
        "scale_name": getattr(song, "scale_name", None),
        "root_note": getattr(song, "root_note", None),
        "scale_mode": getattr(song, "scale_mode", None),
    }


def set_record_mode(surface, params):
    """Set the Arrangement Record button."""
    enabled = bool(_require(params, "enabled"))
    surface._song.record_mode = enabled
    return {"record_mode": bool(surface._song.record_mode)}


def set_session_record(surface, params):
    """Set the Session record/overdub button."""
    enabled = bool(_require(params, "enabled"))
    surface._song.session_record = enabled
    return {"session_record": bool(surface._song.session_record)}


def trigger_session_record(surface, params):
    """Start session recording. record_length in beats stops it automatically."""
    song = surface._song
    if not hasattr(song, "trigger_session_record"):
        raise ValueError("trigger_session_record is not available in this Live version")
    if params.get("record_length") is None:
        song.trigger_session_record()
        length = None
    else:
        length = float(params["record_length"])
        song.trigger_session_record(length)
    return {"triggered": True, "record_length": length}


def set_ableton_link(surface, params):
    """Toggle Ableton Link, and optionally Link start/stop sync."""
    song = surface._song
    if not hasattr(song, "is_ableton_link_enabled"):
        raise ValueError("Ableton Link is not available in this Live version")
    if "enabled" in params:
        song.is_ableton_link_enabled = bool(params["enabled"])
    if "start_stop_sync" in params:
        song.is_ableton_link_start_stop_sync_enabled = bool(params["start_stop_sync"])
    if "enabled" not in params and "start_stop_sync" not in params:
        raise ValueError("Pass enabled or start_stop_sync")
    return {
        "enabled": bool(song.is_ableton_link_enabled),
        "start_stop_sync": bool(getattr(song, "is_ableton_link_start_stop_sync_enabled", False)),
    }


def jump_to_locator(surface, params):
    """Jump the playhead to a cue point by index, name, or time."""
    cues = list(surface._song.cue_points)
    if not cues:
        raise ValueError("Song has no locators")
    cue = None
    if "index" in params:
        index = int(params["index"])
        if index < 0 or index >= len(cues):
            raise IndexError("Locator index {0} out of range".format(index))
        cue = cues[index]
    elif "name" in params:
        needle = str(params["name"]).strip().lower()
        for candidate in cues:
            if str(candidate.name).strip().lower() == needle:
                cue = candidate
                break
        if cue is None:
            raise ValueError("Locator not found: " + str(params["name"]))
    elif "time" in params:
        target = float(params["time"])
        for candidate in cues:
            if abs(float(candidate.time) - target) < 0.001:
                cue = candidate
                break
        if cue is None:
            raise ValueError("No locator at {0}".format(target))
    else:
        raise ValueError("Pass index, name, or time")
    cue.jump()
    return {"name": cue.name, "time": cue.time}


def switch_to_arrangement_view(surface, params):
    """Show and focus Live's Arrangement view."""
    view = surface.application().view
    view.show_view("Arranger")
    if hasattr(view, "focus_view"):
        view.focus_view("Arranger")
    return {"view": "Arranger"}


def capture_and_insert_scene(surface, params):
    """Capture the playing Session clips into a new scene under the selected one."""
    song = surface._song
    if not hasattr(song, "capture_and_insert_scene"):
        raise ValueError("capture_and_insert_scene is not available in this Live version")
    before = len(list(song.scenes))
    song.capture_and_insert_scene()
    return {"captured": True, "scene_count": len(list(song.scenes)), "grew": len(list(song.scenes)) > before}


def try_save_project(surface, params):
    """Save the current set when this Live build exposes a save method.

    The Live Object Model on many versions has no save call. This command tries
    the methods that have shown up on Song and Application and raises if none
    exist, so a client cannot mistake a no-op for a saved set.
    """
    song = surface._song
    try:
        app = surface.application()
    except Exception:
        app = None
    for owner, method_name in (
        (song, "save_current_set"),
        (app, "save_current_set"),
        (song, "save"),
        (app, "save"),
    ):
        if owner is None:
            continue
        method = getattr(owner, method_name, None)
        if callable(method):
            method()
            return {
                "saved": True,
                "method": method_name,
                "file_path": getattr(song, "file_path", ""),
                "name": getattr(song, "name", ""),
            }
    raise ValueError(
        "This Live version exposes no save method. Save from the File menu. "
        "Current set: {0}".format(getattr(song, "file_path", "") or "(unsaved)")
    )


def preview_browser_item(surface, params):
    """Audition a browser item. Playback continues until stop_browser_preview."""
    uri = _require(params, "item_uri") if "item_uri" in params or "uri" not in params else params.get("uri")
    if params.get("uri") and not params.get("item_uri"):
        uri = params["uri"]
    if not uri:
        raise ValueError("Pass item_uri")
    app = surface.application()
    item = surface._find_browser_item_by_uri(app.browser, uri)
    if not item:
        raise ValueError("Browser item with URI '{0}' not found".format(uri))
    app.browser.preview_item(item)
    return {"previewing": True, "name": item.name, "uri": uri}


def stop_browser_preview(surface, params):
    """Stop browser audition playback."""
    surface.application().browser.stop_preview()
    return {"previewing": False}


def batch(surface, params):
    """Run several bridge commands as one undo step.

    commands is a list of {type, params}. Nested batch is rejected.
    stop_on_error (default true) halts the list. undo_on_error (default true)
    calls song.undo() after closing the undo step when Live reports can_undo.
    At most 32 commands.
    """
    commands = params.get("commands")
    if not isinstance(commands, list):
        raise ValueError("batch commands must be a list")
    if len(commands) > MAX_BATCH:
        raise ValueError("batch accepts at most {0} commands".format(MAX_BATCH))
    stop_on_error = bool(params.get("stop_on_error", True))
    undo_on_error = bool(params.get("undo_on_error", True))
    song = surface._song
    undo_open = _begin_undo(song)
    results = []
    try:
        for index, command in enumerate(commands):
            if not isinstance(command, dict) or not command.get("type"):
                raise ValueError("Command {0} must be an object with type".format(index))
            command_type = str(command.get("type"))
            if command_type == "batch":
                raise ValueError("batch cannot contain batch")
            child = command.get("params") or {}
            response = surface._process_command({"type": command_type, "params": child})
            entry = {
                "index": index,
                "type": command_type,
                "status": response.get("status", "success"),
            }
            if response.get("status") == "error":
                entry["message"] = response.get("message", "")
            else:
                entry["result"] = response.get("result", {})
            results.append(entry)
            if entry["status"] == "error" and stop_on_error:
                if undo_open:
                    _end_undo(song)
                    undo_open = False
                undone = False
                if undo_on_error and getattr(song, "can_undo", False):
                    song.undo()
                    undone = True
                return {
                    "stopped_at": index,
                    "undone": undone,
                    "results": results,
                    "error": entry.get("message", ""),
                }
    finally:
        if undo_open:
            _end_undo(song)
    return {"count": len(results), "results": results}


HANDLERS = {
    "batch": batch,
    "capture_and_insert_scene": capture_and_insert_scene,
    "clip_op": clip_op,
    "create_audio_clip": create_audio_clip,
    "create_take_lane": create_take_lane,
    "delete_arrangement_clip": delete_arrangement_clip,
    "duplicate_clip_to": duplicate_clip_to,
    "duplicate_session_clip_to_arrangement": duplicate_session_clip_to_arrangement,
    "get_arrangement_clips": get_arrangement_clips,
    "get_device_routing": get_device_routing,
    "get_master_device_parameters": get_master_device_parameters,
    "get_master_meters": get_master_meters,
    "get_return_device_parameters": get_return_device_parameters,
    "get_session_snapshot": get_session_snapshot,
    "jump_to_locator": jump_to_locator,
    "load_device_to_master": load_device_to_master,
    "load_device_to_return": load_device_to_return,
    "preview_browser_item": preview_browser_item,
    "rack_variation": rack_variation,
    "replace_simpler_sample": replace_simpler_sample,
    "set_ableton_link": set_ableton_link,
    "set_clip_audio": set_clip_audio,
    "set_clip_groove": set_clip_groove,
    "set_clip_signature": set_clip_signature,
    "set_crossfade_assign": set_crossfade_assign,
    "set_device_enabled": set_device_enabled,
    "set_device_routing": set_device_routing,
    "set_drum_pad": set_drum_pad,
    "set_fold_state": set_fold_state,
    "set_loop": set_loop,
    "set_record_mode": set_record_mode,
    "set_send": set_send,
    "set_session_record": set_session_record,
    "set_simpler_playback_mode": set_simpler_playback_mode,
    "set_song_scale": set_song_scale,
    "set_time_signature": set_time_signature,
    "set_track_routing": set_track_routing,
    "stop_browser_preview": stop_browser_preview,
    "switch_to_arrangement_view": switch_to_arrangement_view,
    "trigger_session_record": trigger_session_record,
    "try_save_project": try_save_project,
    "write_automation": write_automation,
}


def lookup(command_type):
    """Return the handler for a gap command, or None."""
    return HANDLERS.get(command_type)
