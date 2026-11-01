"""Apply a DNG's camera field of view to an already-oriented LibRaw decode.

LibRaw develops Ricoh's complete ActiveArea, including DNG pixels outside the
camera JPEG's DefaultCrop. Matching only aspect ratio fails for digital crops.
DefaultCropOrigin is relative to ActiveArea; rawpy's crop margins include the
raw sensor margins. Read both independently and retain those coordinate bases.

``crop_raw_to_camera_frame(scene, dng_path)`` returns ``(crop, metadata)``.
``scene`` must be a full or half-size decode with LibRaw's recorded orientation
already applied (as raw_ops.decode_raw does). The returned crop is a view; no
input pixels or source files are modified. Crop before resizing or tone work.
Only integer-pixel DefaultCrop and square-pixel output are supported explicitly.
This matches field of view, not lens distortion or pixel-level registration.
"""

from __future__ import annotations

from pathlib import Path
import math

import numpy as np
from PIL import Image, TiffImagePlugin


def _integers(values, count: int, name: str) -> list[int]:
    if len(values) != count:
        raise ValueError(f"{name} must contain {count} values")
    result = []
    for value in values:
        number = float(value)
        if not math.isfinite(number) or not number.is_integer():
            raise ValueError(f"{name} must use finite integer pixel coordinates")
        result.append(int(number))
    return result


def _raw_ifd(path: Path) -> dict:
    """Read TIFF/SubIFD metadata without decoding the embedded preview."""
    with Image.open(path) as image:
        root = dict(image.tag_v2)
    if 50706 not in root:
        raise ValueError("A DNG with DNGVersion and explicit DefaultCrop tags is required")
    candidates = []
    pending = [root]
    visited = set()
    with path.open("rb") as handle:
        header = handle.read(16)
        if header[2:4] not in (b"+\x00", b"\x00+"):
            header = header[:8]
        while pending:
            tags = pending.pop()
            if all(key in tags for key in (256, 257, 50719, 50720)):
                candidates.append(tags)
            offsets = tags.get(330, ())
            if isinstance(offsets, int):
                offsets = (offsets,)
            for offset in offsets:
                offset = int(offset)
                if offset in visited:
                    continue
                if len(visited) >= 64:
                    raise ValueError("Unexpectedly deep DNG SubIFD graph")
                visited.add(offset)
                ifd = TiffImagePlugin.ImageFileDirectory_v2(header)
                handle.seek(offset)
                ifd.load(handle)
                pending.append(dict(ifd))
    if not candidates:
        raise ValueError("DNG has no raw IFD with DefaultCropOrigin and DefaultCropSize")
    return max(candidates, key=lambda tags: int(tags[256]) * int(tags[257]))


def camera_crop_metadata(dng_path: str | Path) -> dict:
    """Read the intended DNG crop, active area, and LibRaw orientation.

    This opens the RAW metadata without running demosaicing. Pillow reads the
    DNG tags independently from rawpy's interpreted size and inset-crop fields.
    An inconsistent coordinate interpretation raises instead of guessing.
    """
    import rawpy

    path = Path(dng_path).expanduser().resolve(strict=True)
    tags = _raw_ifd(path)
    raw_width, raw_height = int(tags[256]), int(tags[257])
    area = _integers(tags.get(50829, (0, 0, raw_height, raw_width)), 4, "ActiveArea")
    top, left, bottom, right = area
    origin = _integers(tags[50719], 2, "DefaultCropOrigin")
    size = _integers(tags[50720], 2, "DefaultCropSize")
    default_scale = [float(value) for value in tags.get(50718, (1, 1))]
    if default_scale != [1, 1]:
        raise ValueError("Non-unit DNG DefaultScale needs an explicit geometric resampling model")
    with rawpy.imread(str(path)) as raw:
        sizes = raw.sizes
        active = [int(sizes.width), int(sizes.height)]
        margins = [int(sizes.left_margin), int(sizes.top_margin)]
        inset = [int(sizes.crop_left_margin), int(sizes.crop_top_margin),
                 int(sizes.crop_width), int(sizes.crop_height)]
        flip = int(sizes.flip)
        pixel_aspect = float(sizes.pixel_aspect)
    if active != [right - left, bottom - top] or margins != [left, top]:
        raise ValueError("LibRaw ActiveArea differs from the DNG coordinate basis")
    if pixel_aspect != 1:
        raise ValueError("Non-square LibRaw pixels need explicit geometric resampling")
    raw_rect = [left + origin[0], top + origin[1], *size]
    if inset != raw_rect:
        raise ValueError("LibRaw inset crop and DNG DefaultCrop coordinates disagree")
    record = {
        "source_path": str(path),
        "crop_basis": "DNG DefaultCropOrigin/Size relative to ActiveArea, verified against LibRaw raw inset crop",
        "raw_dimensions": [raw_width, raw_height],
        "active_area_tiff_tlbr": area,
        "active_dimensions": active,
        "active_origin_raw_xy": margins,
        "default_crop_active_xywh": origin + size,
        "default_crop_raw_xywh": raw_rect,
        "libraw_inset_raw_xywh": inset,
        "tiff_default_crop_matches_libraw": True,
        "default_scale": default_scale,
        "libraw_flip": flip,
        "orientation_basis": "LibRaw flip already applied to decoded pixels; transform crop coordinates only",
        "registration_limit": "Matching DNG field of view does not register lens distortion or local image geometry",
    }
    _crop_geometry(record)
    return record


def _crop_geometry(metadata: dict) -> tuple[int, int, list[int]]:
    width, height = _integers(metadata["active_dimensions"], 2, "active_dimensions")
    x, y, crop_width, crop_height = _integers(metadata["default_crop_active_xywh"], 4, "DefaultCrop")
    if min(width, height, crop_width, crop_height) <= 0 or min(x, y) < 0:
        raise ValueError("DefaultCrop dimensions must be positive and origin nonnegative")
    if x + crop_width > width or y + crop_height > height:
        raise ValueError("DefaultCrop extends outside the active sensor area")
    flip = int(metadata["libraw_flip"])
    if flip != metadata["libraw_flip"] or not 0 <= flip <= 7:
        raise ValueError("LibRaw flip must be an integer in 0..7")
    x0, y0, x1, y1 = x, y, x + crop_width, y + crop_height
    # LibRaw's flags mirror the sensor axes, then transpose. In particular:
    # 3 = 180 degrees, 5 = 90 CCW, 6 = 90 CW, matching rawpy's user_flip API.
    if flip & 1:
        x0, x1 = width - x1, width - x0
    if flip & 2:
        y0, y1 = height - y1, height - y0
    if flip & 4:
        x0, y0, x1, y1 = y0, x0, y1, x1
        width, height = height, width
    return width, height, [x0, y0, x1, y1]


def apply_camera_crop(scene: np.ndarray, metadata: dict) -> tuple[np.ndarray, dict]:
    """Apply previously read metadata to a full/half, already-oriented decode."""
    image = np.asarray(scene)
    if image.ndim != 3 or image.shape[2] != 3 or not all(image.shape[:2]):
        raise ValueError("scene must be a nonempty H x W x 3 already-oriented decode")
    width, height, full_rect = _crop_geometry(metadata)
    if image.shape[:2] == (height, width):
        scale = 1.0
    elif image.shape[:2] == ((height + 1) // 2, (width + 1) // 2):
        scale = .5
    else:
        raise ValueError("scene dimensions must match full or half-size oriented LibRaw ActiveArea; crop before resizing")
    applied = [round(value * scale) for value in full_rect]
    x0, y0, x1, y1 = applied
    if x1 <= x0 or y1 <= y0:
        raise ValueError("DefaultCrop becomes empty at this decode scale")
    result = image[y0:y1, x0:x1]
    record = {**metadata,
              "decoded_dimensions": [image.shape[1], image.shape[0]],
              "decode_scale": scale,
              "oriented_crop_fullres_xyxy": full_rect,
              "applied_crop_xyxy": applied,
              "rounding": "nearest integer pixel boundary; half-to-even for half-size odd boundaries",
              "cropped_dimensions": [result.shape[1], result.shape[0]]}
    return result, record


def crop_raw_to_camera_frame(scene: np.ndarray, dng_path: str | Path) -> tuple[np.ndarray, dict]:
    """Crop an oriented LibRaw scene to the DNG's declared camera field of view."""
    return apply_camera_crop(scene, camera_crop_metadata(dng_path))
