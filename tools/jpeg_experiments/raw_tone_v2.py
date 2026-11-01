"""Explicit scene-exposure film tone curves for an offline RAW experiment.

Input is nonnegative, scene-linear sRGB (including values above one), normally
from ``raw_ops.decode_raw`` with its recorded camera WB. Output is display sRGB
float32 in [0, 1]. The curves directly produce display code values: do not apply
another sRGB transfer function. They have a toe, midtone slope and asymptotic
shoulder across the full scene range, rather than treating only highlights.

These are creative tone families, not measured named film stocks, camera JPEG
emulation, or a recovery algorithm. Compare the resulting look primarily with
the same frame's actual camera JPEG. The standard reference is simply a common
conventional S curve for isolating these changes on the same RAW decode.

No white balance, local adjustment, automatic brightness, target matching,
denoising, sharpening or grain is applied. Exposure is the explicit multiplier
provided by the caller. Per-channel curves retain neutral RGB but can change
colour saturation and hue; the coloured shoulder is a creative rendering, not
a claim of colourimetric hue preservation.
"""

from __future__ import annotations

import numpy as np


# Parameters: display black, asymptotic display white, display value for scene
# middle grey 0.18, and slope parameter of the log-exposure sigmoid. They are
# all output code values, so the toe's raised black has an explicit meaning.
_REFERENCE = np.array([0.0, 1.0, 0.48, 1.10], dtype=np.float64)
_FILM = {
    "negative": np.array([0.035, 0.975, 0.53, 1.80], dtype=np.float64),
    "fade": np.array([0.100, 0.920, 0.56, 0.95], dtype=np.float64),
    "contrast": np.array([0.000, 1.000, 0.46, 2.00], dtype=np.float64),
}


def _finite_number(value: float, name: str, high: float = np.inf) -> float:
    value = float(value)
    if not np.isfinite(value) or not 0 <= value <= high:
        raise ValueError(f"{name} must be finite and between 0 and {high}")
    return value


def _scene(scene: np.ndarray, exposure: float) -> np.ndarray:
    exposure = _finite_number(exposure, "exposure")
    with np.errstate(over="ignore", invalid="ignore"):
        source = np.asarray(scene, dtype=np.float32)
    if source.ndim < 1 or source.shape[-1] != 3 or source.size == 0:
        raise ValueError("scene must be a nonempty RGB array with last dimension 3")
    if not np.isfinite(source).all() or np.any(source < 0):
        raise ValueError("scene must contain finite nonnegative linear RGB values")
    # Float64 avoids overflow for a valid high scene value and exposure factor.
    # Working storage is private, so a read-only source is safe as well.
    exposed = source.astype(np.float64) * exposure
    if not np.isfinite(exposed).all():
        raise ValueError("exposed scene must remain finite")
    return exposed


def _curve(exposed: np.ndarray, parameters: np.ndarray) -> np.ndarray:
    black, white, middle, contrast = parameters
    position = (middle - black) / (white - black)
    # For x>0: black + (white-black) / (1 + a*(0.18/x)**contrast),
    # with a=(1-position)/position. Evaluating in log exposure keeps huge input
    # headroom finite. tanh is the stable logistic and maps log(0)=-inf to black.
    log_exposure = np.full_like(exposed, -np.inf)
    np.log(exposed, out=log_exposure, where=exposed > 0)
    log_odds = contrast * (log_exposure - np.log(0.18)) + np.log(position / (1 - position))
    encoded = black + (white - black) * (0.5 + 0.5 * np.tanh(0.5 * log_odds))
    return np.clip(encoded, 0.0, 1.0).astype(np.float32)


def render_reference_standard(scene: np.ndarray, exposure: float = 1.0) -> np.ndarray:
    """Render one declared ordinary contrast curve with a soft white shoulder.

    It maps scene black to 0, scene 0.18 to display 0.48 and approaches display
    1 as scene exposure rises; values above scene 1 remain distinct. This is
    not the Ricoh Standard engine, a matched camera JPEG, or a neutral encoding.
    """
    return _curve(_scene(scene, exposure), _REFERENCE)


def render_film_tone(scene: np.ndarray, style: str = "negative",
                     exposure: float = 1.0, strength: float = 1.0) -> np.ndarray:
    """Render an explicit film-style toe, midtone contrast and shoulder.

    ``negative`` has a small raised black, firm midtone contrast and a lowered
    creamy white; ``fade`` opens the toe and lowers the white for milky blacks;
    ``contrast`` gives deeper shadows and a steeper middle. All have smooth
    shoulders using decoded RAW headroom, with no source-dependent matching.

    Strength is 0..2: 0 is the common ``render_reference_standard`` curve,
    1 the declared profile, and 2 extrapolates its parameters to an intentionally
    overdone look. It is not a blend with hard clipping. Exposure is a linear
    multiplier (1 unchanged, 2 +1 stop, 0.5 -1 stop); zero exposure renders the
    selected curve's black level. No inputs are mutated.
    """
    if not isinstance(style, str) or style not in _FILM:
        raise ValueError("style must be 'negative', 'fade', or 'contrast'")
    strength = _finite_number(strength, "strength", high=2.0)
    parameters = _REFERENCE + strength * (_FILM[style] - _REFERENCE)
    return _curve(_scene(scene, exposure), parameters)
