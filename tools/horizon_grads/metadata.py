"""Bounded read-only GR III MakerNote audit; no general EXIF writer.

0x022b in this collection has the newer 19-byte format: state/format byte at 0,
direction at 1, signed little-endian roll/pitch at 3/5, -raw/2 degrees.
Source for the field layout and unit: ExifTool Pentax.pm LevelInfoK3III.
ExifTool's older LevelInfo decoder must NOT be used for these records.
The layout match and gravity-vector agreement are evidence, not a Ricoh
specification or a calibrated level accuracy claim.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
import struct

from PIL import Image

SOURCES = (Path("C:/Users/Antoine/Pictures/Ricoh"), Path("C:/Users/Antoine/Pictures/Ricoh2"))


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def safe_output(path: Path, sources=SOURCES) -> Path:
    target = path.resolve()
    for source in sources:
        root = source.resolve()
        if target == root or root in target.parents:
            raise ValueError(f"Output must be outside original source tree: {root}")
    return target


def decode_level(note: bytes) -> dict:
    invalid = {"valid": False, "reason": "missing or unsupported Ricoh MakerNote"}
    if not isinstance(note, bytes) or len(note) < 10 or note[:8] != b"RICOH\0II":
        return invalid
    count = struct.unpack_from("<H", note, 8)[0]
    if 10 + 12 * count + 4 > len(note):
        return {**invalid, "reason": "truncated MakerNote IFD"}
    matches = []
    for pos in range(10, 10 + 12 * count, 12):
        tag, kind, size, offset = struct.unpack_from("<HHII", note, pos)
        if tag == 0x022b:
            matches.append((kind, size, offset))
    if len(matches) != 1:
        return {**invalid, "reason": "missing or duplicate LevelInfo tag"}
    kind, size, offset = matches[0]
    if kind != 7 or size != 19 or offset < 10 + 12 * count + 4 or offset + size > len(note):
        return {**invalid, "reason": "unsupported or truncated LevelInfo payload"}
    block = note[offset:offset + size]
    r, p = struct.unpack_from("<hh", block, 3)
    result = {"level_tag": "0x022b", "level_type": kind, "level_length": size,
              "maker_relative_offset": offset, "raw_level_hex": block.hex(),
              # "version" is the audit's provisional name, not a traced field
              # semantic. State 0 also carries plausible angles; this prototype
              # conservatively accepts only state 1 until that flag is traced.
              "version": block[0], "camera_orientation": block[1],
              "raw_roll_i16": r, "raw_pitch_i16": p,
              "roll_deg": -r / 2, "pitch_deg": -p / 2,
              "unit_interpretation": "signed int16 little-endian; -raw/2 degrees; roll relative to cardinal orientation"}
    if block[0] != 1:
        return {**result, "valid": False, "reason": "level state/format byte is not 1 (semantics untraced)"}
    if block[1] not in range(4):
        return {**result, "valid": False, "reason": "up/down or unknown cardinal orientation"}
    if abs(r / 2) > 45 or abs(p / 2) > 90:
        return {**result, "valid": False, "reason": "angle outside supported residual-roll/pitch range"}
    return {**result, "valid": True, "reason": "supported 19-byte level layout"}


def read_metadata(path: Path) -> dict:
    with Image.open(path) as im:
        exif = im.getexif()
        detail = exif.get_ifd(34665)
        result = decode_level(detail.get(37500, b""))
        orientation = int(exif.get(274, 1))
        focal = float(detail.get(37386, 0))
        focal35 = float(detail.get(41989, 0))
        result.update({"camera": str(exif.get(272, "")).strip(), "software": str(exif.get(305, "")).strip(),
                       "exif_orientation": orientation, "stored_size": list(im.size),
                       "display_size": list(reversed(im.size)) if orientation in (6, 8) else list(im.size),
                       "focal_mm": focal, "focal35_mm": focal35,
                       "colour_space": detail.get(40961), "has_icc": bool(im.info.get("icc_profile"))})
        if result["valid"] and {0: 1, 1: 8, 2: 3, 3: 6}[result["camera_orientation"]] != orientation:
            result.update(valid=False, reason="level cardinal orientation disagrees with EXIF")
        if result["valid"] and (result["camera"] != "RICOH GR III" or abs(focal - 18.3) > 0.05 or focal35 not in (28, 35, 50)):
            result.update(valid=False, reason="camera, lens or digital crop is outside supported GR III geometry")
        # A close-to-full-frame image is required; crop ratios use EXIF effective focal length.
        ratio = im.width / im.height
        if result["valid"] and abs(ratio - 1.5) > 0.01:
            result.update(valid=False, reason="unsupported aspect crop; optical centre not established")
    return result
