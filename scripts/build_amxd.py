#!/usr/bin/env python3
"""build_amxd.py - package a .maxpat source file into a Max for Live device (.amxd).

The .amxd container is a chunk list: each chunk is a 4-byte ASCII id, a
little-endian uint32 payload size, then the payload bytes (Ableton's own
reference parser, maxdevtools/maxdiff, reads it exactly this way).

    "ampf" + uint32(4) + b"aaaa"      device type: aaaa audio / mmmm MIDI / iiii instrument
    "meta" + uint32(4) + uint32(0)    metadata chunk
    "ptch" + uint32(N) + patcher JSON patcher, NUL terminated

Usage:
    python scripts/build_amxd.py                          # AbletonMCP_M4L/AbletonMCP.amxd.maxpat
    python scripts/build_amxd.py source.maxpat -o out.amxd --device-type midi
    python scripts/build_amxd.py --verify                 # build, then parse the result back
"""

from __future__ import annotations

import argparse
import json
import struct
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MAXPAT = REPO_ROOT / "AbletonMCP_M4L" / "AbletonMCP.amxd.maxpat"

DEVICE_TYPES = {
    "audio": b"aaaa",
    "midi": b"mmmm",
    "instrument": b"iiii",
}


def _read_patcher_bytes(maxpat_path: Path) -> bytes:
    """Return the patcher JSON exactly as written, minus any UTF-8 BOM."""
    raw = maxpat_path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        raw = raw[3:]
    try:
        document = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SystemExit(f"error: {maxpat_path} is not valid UTF-8 JSON: {exc}") from exc
    if "patcher" not in document:
        raise SystemExit(f"error: {maxpat_path} has no top-level 'patcher' object")

    # An empty parameterbanks block combined with parameter_enable on live.*
    # objects trips a crash in Max's param_banks_fromdictionary on device load.
    parameters = document["patcher"].get("parameters") or {}
    banks = parameters.get("parameterbanks") or {}
    if banks and all(not bank.get("parameters") for bank in banks.values()):
        print(
            "warning: empty 'parameterbanks' block - remove the top-level "
            "'parameters' key from the .maxpat to avoid a device-load crash",
            file=sys.stderr,
        )
    return raw


def build_maxpat_to_amxd(maxpat_path: Path, amxd_path: Path, device_type: str = "audio") -> int:
    """Write amxd_path from maxpat_path. Returns the number of bytes written."""
    patcher = _read_patcher_bytes(maxpat_path)
    if not patcher.endswith(b"\x00"):
        patcher += b"\x00"

    header = (
        b"ampf" + struct.pack("<I", 4) + DEVICE_TYPES[device_type]
        + b"meta" + struct.pack("<I", 4) + struct.pack("<I", 0)
        + b"ptch" + struct.pack("<I", len(patcher))
    )
    amxd_path.parent.mkdir(parents=True, exist_ok=True)
    payload = header + patcher
    amxd_path.write_bytes(payload)
    return len(payload)


def read_amxd(amxd_path: Path) -> tuple[bytes, dict]:
    """Parse an .amxd back into (device type chunk, patcher document)."""
    data = amxd_path.read_bytes()
    offset = 0
    device_type = b""
    patcher_bytes = b""
    while offset + 8 <= len(data):
        field = data[offset:offset + 4]
        size = struct.unpack("<I", data[offset + 4:offset + 8])[0]
        offset += 8
        chunk = data[offset:offset + size]
        offset += size
        if field == b"ampf":
            device_type = chunk
        elif field == b"ptch":
            patcher_bytes = chunk
    if not device_type or not patcher_bytes:
        raise SystemExit(f"error: {amxd_path} is not a readable .amxd container")
    if patcher_bytes.endswith(b"\x00"):
        patcher_bytes = patcher_bytes[:-1]
    return device_type, json.loads(patcher_bytes.decode("utf-8"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a Max for Live .amxd from a .maxpat source.")
    parser.add_argument("maxpat", nargs="?", default=str(DEFAULT_MAXPAT), help="source .maxpat file")
    parser.add_argument("-o", "--output", help="output .amxd file (default: source name without .maxpat)")
    parser.add_argument(
        "--device-type",
        default="audio",
        choices=sorted(DEVICE_TYPES),
        help="Max for Live device type (default: audio)",
    )
    parser.add_argument("--verify", action="store_true", help="parse the written device back and report it")
    args = parser.parse_args(argv)

    maxpat_path = Path(args.maxpat)
    if not maxpat_path.is_file():
        raise SystemExit(f"error: source patch not found: {maxpat_path}")

    output_path = Path(args.output) if args.output else maxpat_path.with_name(
        maxpat_path.name[: -len(".maxpat")] if maxpat_path.name.endswith(".maxpat") else maxpat_path.stem + ".amxd"
    )

    written = build_maxpat_to_amxd(maxpat_path, output_path, args.device_type)
    source_doc = json.loads(_read_patcher_bytes(maxpat_path).decode("utf-8"))
    print(f"device type : {args.device_type} ({DEVICE_TYPES[args.device_type].decode()})")
    print(f"source      : {maxpat_path} ({maxpat_path.stat().st_size} bytes)")
    print(f"output      : {output_path} ({written} bytes)")
    print(
        "objects     : "
        f"{len(source_doc['patcher'].get('boxes', []))} boxes, "
        f"{len(source_doc['patcher'].get('lines', []))} patch cords"
    )

    if args.verify:
        device_type, document = read_amxd(output_path)
        patcher = document.get("patcher", {})
        if device_type != DEVICE_TYPES[args.device_type]:
            raise SystemExit(f"error: device type mismatch in {output_path}")
        if len(patcher.get("boxes", [])) != len(source_doc["patcher"].get("boxes", [])):
            raise SystemExit(f"error: object count mismatch in {output_path}")
        print(
            "verified    : "
            f"{device_type.decode()} device, {len(patcher.get('boxes', []))} objects, "
            f"devicewidth={patcher.get('devicewidth')}, "
            f"openinpresentation={patcher.get('openinpresentation')}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
