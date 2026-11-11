"""Deterministic graduated filter prototype in normalized upright sRGB.

This is an earth-horizon mask, not sky segmentation. Objects above the earth
horizon and indoor ceilings can be affected. The brightness option merely
reduces changes on dark objects; it cannot identify trees, sky or buildings.
"""
from __future__ import annotations

import math

import numpy as np

STYLES = {
    "neutral": (1.0, 1.0, 1.0),
    "tobacco": (0.52, 1.05, 1.85),
    "sunset": (0.40, 1.25, 1.95),
    "blue": (1.70, 1.00, 0.42),
}


def focal_pixels(width: int, height: int, focal_mm: float, focal35_mm: float) -> float:
    """Focal length in pixels of the stored sensor image, before EXIF rotation.

    Compute once from stored dimensions and uniformly scale when resizing. A
    quarter-turn changes the output dimensions but does not change focal_px.
    """
    if width <= 0 or height <= 0 or focal_mm <= 0 or focal35_mm <= 0:
        raise ValueError("Positive dimensions and focal lengths required")
    # GR III 23.5 x 15.6 mm active area; inscribe exact JPEG aspect inside it.
    # EXIF 28/35/50 mm is treated as a centred digital crop relative to 28 mm.
    sensor_w = min(23.5, 15.6 * width / height) * 28 / focal35_mm
    return width * focal_mm / sensor_w


def horizon_distance(width: int, height: int, focal_px: float, roll_deg: float, pitch_deg: float) -> np.ndarray:
    """Signed perpendicular pixel distance to the ideal horizon, positive above.

    Ray coordinates x right, y down, z forward. For clockwise camera roll r,
    upward pitch p: up=(-cos(p)sin(r), -cos(p)cos(r), sin(p)). The horizon
    is up dot (x,y,f) == 0. Divide by cos(p) to get this affine distance.
    Roll here is the residual after EXIF cardinal rotation; f is unchanged.
    """
    if not all(math.isfinite(v) for v in (focal_px, roll_deg, pitch_deg)) or focal_px <= 0 or abs(pitch_deg) >= 89:
        raise ValueError("Finite focal length and nonvertical pitch required")
    r, p = math.radians(roll_deg), math.radians(pitch_deg)
    x = np.arange(width, dtype=np.float32)[None, :] - (width - 1) / 2
    y = np.arange(height, dtype=np.float32)[:, None] - (height - 1) / 2
    return (focal_px * math.tan(p) - math.sin(r) * x - math.cos(r) * y).astype(np.float32)


def smoothstep(v):
    v = np.clip(v, 0, 1)
    return v * v * (3 - 2 * v)


def make_mask(width: int, height: int, metadata: dict, transition_deg=16.0) -> np.ndarray:
    zero = np.zeros((height, width), dtype=np.float32)
    if not metadata.get("valid"):
        return zero
    p, r, f = (metadata.get(k, float("nan")) for k in ("pitch_deg", "roll_deg", "focal_px"))
    if not all(math.isfinite(v) for v in (p, r, f)) or f <= 0 or abs(p) >= 65 or abs(r) > 45:
        return zero
    if not math.isfinite(transition_deg) or not 0 < transition_deg < 80:
        raise ValueError("Transition angle must be between 0 and 80 degrees")
    distance = horizon_distance(width, height, f, r, p)
    fade = float(1 - smoothstep((abs(p) - 35) / 30))
    return (smoothstep(distance / (f * math.tan(math.radians(transition_deg)))) * fade).astype(np.float32)


def brightness_weight(rgb: np.ndarray) -> np.ndarray:
    # Deliberately display-luminance based, not a blue/green/skin classifier.
    luma = rgb @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)
    return smoothstep((luma - 0.12) / (0.55 - 0.12)).astype(np.float32)


def apply_grad(rgb: np.ndarray, mask: np.ndarray, style="neutral", stops=1.0, weighted=False) -> np.ndarray:
    if style == "off" or stops == 0:
        return rgb.copy()
    if style not in STYLES or not math.isfinite(stops) or not 0 <= stops <= 3:
        raise ValueError("Unknown style or unsupported strength")
    if rgb.ndim != 3 or rgb.shape[2] != 3 or mask.shape != rgb.shape[:2]:
        raise ValueError("RGB and mask dimensions must agree")
    if not np.isfinite(rgb).all() or not np.isfinite(mask).all():
        raise ValueError("Non-finite pixels or mask")
    weight = np.clip(mask, 0, 1)
    if weighted:
        weight = weight * brightness_weight(rgb)
    # Optical-density style channel attenuation; no generated pixels or global
    # colour remapping. A neutral stop gives exactly 0.5 in linear light.
    linear = np.where(rgb <= 0.04045, rgb / 12.92, ((rgb + 0.055) / 1.055) ** 2.4)
    gains = np.exp2(-stops * weight[..., None] * np.asarray(STYLES[style], dtype=np.float32))
    linear *= gains
    out = np.where(linear <= 0.0031308, linear * 12.92, 1.055 * np.maximum(linear, 0) ** (1 / 2.4) - 0.055)
    # Exact unchanged pixels outside the mask, before re-encoding.
    return np.where(weight[..., None] > 0, np.clip(out, 0, 1), rgb).astype(np.float32)
