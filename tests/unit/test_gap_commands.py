"""Handlers for the Enableton bridge commands this Remote Script was missing.

The Live script cannot be imported here (_Framework only exists inside Live),
so the tests load enableton_commands.py directly and drive it with fakes.
"""

import json
import re
from importlib.machinery import SourceFileLoader
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
MODULE = SourceFileLoader(
    "enableton_gap_commands",
    str(ROOT / "AbletonMCP_Remote_Script" / "enableton_commands.py"),
).load_module()


class Param(object):
    def __init__(self, name, value=0.0, minimum=0.0, maximum=1.0):
        self.name = name
        self.value = value
        self.min = minimum
        self.max = maximum
        self.is_enabled = True
        self.is_quantized = False


class Envelope(object):
    def __init__(self):
        self.points = []
        self.cleared = False

    def clear(self):
        self.cleared = True
        self.points = []

    def insert_value(self, time, value):
        self.points.append((time, value))


class Clip(object):
    def __init__(self, name="Clip", start=0.0, end=4.0):
        self.name = name
        self.start_time = start
        self.end_time = end
        self.length = end - start
        self.color = 0
        self.muted = False
        self.is_midi_clip = True
        self.is_audio_clip = False
        self.signature_numerator = 4
        self.signature_denominator = 4
        self.envelope = Envelope()
        self.cropped = False
        self.groove = None
        self.has_groove = False

    def create_automation_envelope(self, param):
        self.envelope_param = param
        return self.envelope

    def crop(self):
        self.cropped = True


class Slot(object):
    def __init__(self, clip=None):
        self.clip = clip
        self.has_clip = clip is not None
        self.created_path = None
        self.deleted = False

    def delete_clip(self):
        self.deleted = True
        self.clip = None
        self.has_clip = False

    def create_audio_clip(self, path):
        self.created_path = path
        self.clip = Clip(name="Audio")
        self.clip.is_midi_clip = False
        self.clip.is_audio_clip = True
        self.clip.sample_rate = 44100
        self.clip.sample_length = 100
        self.clip.warping = False
        self.has_clip = True

    def duplicate_clip_to(self, target):
        target.clip = self.clip
        target.has_clip = True


class Mixer(object):
    def __init__(self):
        self.volume = Param("Volume", 0.8)
        self.panning = Param("Pan", 0.0, -1.0, 1.0)
        self.sends = [Param("Send A", 0.0)]
        self.crossfade_assign = 1


class Device(object):
    def __init__(self, name="EQ", class_name="Eq8", on=True):
        self.name = name
        self.class_name = class_name
        self.can_have_chains = False
        self.can_have_drum_pads = False
        self.parameters = [Param("Device On", 1.0 if on else 0.0)]


class Track(object):
    def __init__(self, name="Track", audio=True):
        self.name = name
        self.has_audio_input = audio
        self.is_frozen = False
        self.mute = False
        self.solo = False
        self.is_foldable = False
        self.fold_state = 0
        self.mixer_device = Mixer()
        self.clip_slots = [Slot(Clip())]
        self.devices = [Device()]
        self.arrangement_clips = []
        self.deleted = []
        self.duplicated = []
        self.view = type("View", (), {"is_collapsed": False})()

    def delete_clip(self, clip):
        self.deleted.append(clip)
        self.arrangement_clips = [item for item in self.arrangement_clips if item is not clip]

    def duplicate_clip_to_arrangement(self, clip, time):
        copy = Clip(clip.name, time, time + clip.length)
        self.arrangement_clips.append(copy)
        self.duplicated.append((clip, time))

    def create_audio_clip(self, path, position):
        self.arrangement_created = (path, position)


class Cue(object):
    def __init__(self, name, time):
        self.name = name
        self.time = time
        self.jumped = False

    def jump(self):
        self.jumped = True


class Song(object):
    def __init__(self, track):
        self.tracks = [track]
        self.return_tracks = []
        self.master_track = Track("Master")
        self.master_track.output_meter_left = 0.2
        self.master_track.output_meter_right = 0.3
        self.scenes = []
        self.cue_points = [Cue("Drop", 16.0), Cue("Verse", 0.0)]
        self.tempo = 120.0
        self.is_playing = False
        self.current_song_time = 0.0
        self.signature_numerator = 4
        self.signature_denominator = 4
        self.loop = False
        self.loop_start = 0.0
        self.loop_length = 8.0
        self.record_mode = False
        self.session_record = False
        self.scale_name = "Major"
        self.scale_mode = True
        self.root_note = 0
        self.is_ableton_link_enabled = False
        self.is_ableton_link_start_stop_sync_enabled = False
        self.can_undo = True
        self.undo_open = False
        self.undone = False
        self.view = type("View", (), {"selected_track": None})()

    def begin_undo_step(self):
        self.undo_open = True

    def end_undo_step(self):
        self.undo_open = False

    def undo(self):
        self.undone = True

    def capture_and_insert_scene(self):
        self.scenes.append(type("Scene", (), {"name": "Captured"})())

    def trigger_session_record(self, length=None):
        self.triggered = length


class Surface(object):
    def __init__(self):
        self.track = Track()
        self._song = Song(self.track)

    def _process_command(self, command):
        if command["type"] == "boom":
            return {"status": "error", "message": "boom"}
        return {"status": "success", "result": {"type": command["type"]}}


def test_handlers_match_the_port_report():
    report = json.loads((ROOT / "docs" / "enableton-port-report.json").read_text(encoding="utf-8"))
    assert set(MODULE.HANDLERS) == set(report["missing_commands"])
    assert MODULE.READ_COMMANDS <= set(MODULE.HANDLERS)
    assert len(MODULE.HANDLERS) == 42


def test_rest_whitelist_includes_every_gap_command():
    import rest_api_server

    missing = [name for name in MODULE.HANDLERS if name not in rest_api_server.ALLOWED_COMMANDS]
    assert missing == []


def test_mcp_wrappers_cover_every_command_except_the_existing_snapshot():
    """Source check. Importing the server pulls an mcp build this lockfile may not have."""
    text = (ROOT / "MCP_Server" / "gap_commands.py").read_text(encoding="utf-8")
    defined = set(re.findall(r"^def ([a-z][a-z0-9_]*)\(", text, re.M))
    defined.discard("register_gap_commands")
    assert defined == set(MODULE.HANDLERS) - {"get_session_snapshot"}
    write_block = text.split("WRITE_COMMANDS", 1)[1].split("})", 1)[0]
    writes = set(re.findall(r'"([a-z0-9_]+)"', write_block))
    assert writes == set(MODULE.HANDLERS) - MODULE.READ_COMMANDS
    assert "get_session_snapshot" not in writes


def test_get_arrangement_clips_and_delete():
    surface = Surface()
    surface.track.arrangement_clips = [Clip("Intro", 0.0, 8.0), Clip("Drop", 16.0, 32.0)]
    listed = MODULE.get_arrangement_clips(surface, {"track_index": 0})
    assert listed["clip_count"] == 2
    assert listed["clips"][1]["name"] == "Drop"

    deleted = MODULE.delete_arrangement_clip(surface, {"track_index": 0, "start_time": 16.0})
    assert deleted["name"] == "Drop"
    assert [clip.name for clip in surface.track.arrangement_clips] == ["Intro"]


def test_duplicate_session_clip_to_arrangement():
    surface = Surface()
    result = MODULE.duplicate_session_clip_to_arrangement(
        surface, {"track_index": 0, "clip_index": 0, "destination_time": 32.0}
    )
    assert result["grew"] is True
    assert result["clip"]["start_time"] == 32.0
    assert surface.track.duplicated[0][1] == 32.0


def test_create_audio_clip_rejects_a_missing_file(tmp_path):
    surface = Surface()
    with pytest.raises(ValueError, match="not found"):
        MODULE.create_audio_clip(surface, {
            "track_index": 0,
            "clip_index": 1,
            "file_path": str(tmp_path / "missing.wav"),
        })


def test_create_audio_clip_in_an_empty_session_slot(tmp_path):
    audio = tmp_path / "kick.wav"
    audio.write_bytes(b"RIFF")
    surface = Surface()
    surface.track.clip_slots.append(Slot())
    result = MODULE.create_audio_clip(surface, {
        "track_index": 0,
        "clip_index": 1,
        "file_path": str(audio),
        "name": "Kick",
    })
    assert result["where"] == "session"
    assert result["name"] == "Kick"
    assert surface.track.clip_slots[1].created_path == str(audio)


def test_song_setters_and_locator_jump():
    surface = Surface()
    signature = MODULE.set_time_signature(surface, {"numerator": 7, "denominator": 8})
    assert signature == {"numerator": 7, "denominator": 8}
    loop = MODULE.set_loop(surface, {"enabled": True, "start": 4.0, "length": 16.0})
    assert loop["loop"] is True
    assert loop["loop_start"] == 4.0
    jumped = MODULE.jump_to_locator(surface, {"name": "Drop"})
    assert jumped["time"] == 16.0
    assert surface._song.cue_points[0].jumped is True
    scale = MODULE.set_song_scale(surface, {"scale_name": "Minor", "root_note": 9})
    assert scale["scale_name"] == "Minor"
    assert scale["root_note"] == 9


def test_batch_stops_and_undoes():
    surface = Surface()
    result = MODULE.batch(surface, {"commands": [
        {"type": "set_tempo", "params": {"tempo": 100}},
        {"type": "boom", "params": {}},
        {"type": "set_tempo", "params": {"tempo": 90}},
    ]})
    assert result["stopped_at"] == 1
    assert result["undone"] is True
    assert surface._song.undo_open is False
    assert len(result["results"]) == 2
    with pytest.raises(ValueError, match="cannot contain batch"):
        MODULE.batch(surface, {"commands": [{"type": "batch", "params": {}}]})


def test_device_enable_fold_send_and_automation():
    surface = Surface()
    enabled = MODULE.set_device_enabled(surface, {"track_index": 0, "device_index": 0, "enabled": False})
    assert enabled["value"] == 0
    surface.track.is_foldable = True
    folded = MODULE.set_fold_state(surface, {"track_index": 0, "folded": True})
    assert folded["fold_state"] == 1
    send = MODULE.set_send(surface, {"track_index": 0, "send_index": 0, "value": 0.4})
    assert send["value"] == 0.4
    written = MODULE.write_automation(surface, {
        "track_index": 0,
        "clip_index": 0,
        "parameter_name": "Device On",
        "points": [{"time": 0.0, "value": 1.0}, {"time": 2.0, "value": 5.0}],
    })
    assert written["points_written"] == 2
    assert surface.track.clip_slots[0].clip.envelope.cleared is True
    # 5.0 is clamped to the parameter max of 1.0
    assert surface.track.clip_slots[0].clip.envelope.points[1] == (2.0, 1.0)


def test_clip_op_and_crossfade_and_save():
    surface = Surface()
    cropped = MODULE.clip_op(surface, {"track_index": 0, "clip_index": 0, "operation": "crop"})
    assert cropped["operation"] == "crop"
    assert surface.track.clip_slots[0].clip.cropped is True
    assigned = MODULE.set_crossfade_assign(surface, {"track_index": 0, "assign": "B"})
    assert assigned["crossfade_assign"] == 2
    with pytest.raises(ValueError, match="File menu"):
        MODULE.try_save_project(surface, {})
    surface._song.save_current_set = lambda: setattr(surface._song, "saved", True)
    saved = MODULE.try_save_project(surface, {})
    assert saved["method"] == "save_current_set"
    assert surface._song.saved is True


def test_replace_simpler_sample_uses_a_load_method(tmp_path):
    audio = tmp_path / "sample.wav"
    audio.write_bytes(b"RIFF")
    surface = Surface()
    simpler = Device("Simpler", "OriginalSimpler")
    loaded = {}

    def load_sample(path):
        loaded["path"] = path

    simpler.load_sample = load_sample
    surface.track.devices = [simpler]
    result = MODULE.replace_simpler_sample(surface, {"track_index": 0, "file_path": str(audio)})
    assert result["method"] == "load_sample"
    assert loaded["path"] == str(audio)


def test_session_snapshot_and_master_meters():
    surface = Surface()
    snapshot = MODULE.get_session_snapshot(surface, {})
    assert snapshot["track_count"] == 1
    assert snapshot["tracks"][0]["name"] == "Track"
    assert snapshot["tempo"] == 120.0
    meters = MODULE.get_master_meters(surface, {})
    assert meters["output_meter_left"] == 0.2
    assert meters["output_meter_right"] == 0.3
