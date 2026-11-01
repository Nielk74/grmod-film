"""Film targets from measured stock data: a simplified negative -> print (or slide) model.

    python film_datasheet_v3.py PROFILE_DIR THETA.npy OUT_DIR

PROFILE_DIR holds stock profiles (JSON: spectral log sensitivities, density curves, dye spectra) from the
spektrafilm project (CC BY-SA 4.0, Andrea Volpato, https://github.com/andreavolpato/spektrafilm). Only
the data is read; the model below is written from textbook sensitometry (Hunt, The Reproduction of
Colour, ch. 15) and is much simpler than spektrafilm's (no masking couplers, no spectral upsampling
beyond a linear sRGB basis, no grain/halation). Research use only: the profiles' licence is
share-alike, and GR Mod is GPL-2.0-only; shipping looks derived from them needs a decision.

Chain, for a camera-Standard display colour:
 1. Standard display -> scene linear sRGB: the calibrated GR III Standard model (fitted on the user's
    37 Standard DNG/JPEG pairs) inverted, at a typical exposure gain;
 2. scene reflectance as Mallett-Yuksel sRGB basis spectra, lit by the scene illuminant;
 3. each film layer's exposure (its spectral sensitivity), density from its characteristic curve,
    plus an interlayer (DIR) term that pushes layer densities apart (purer colour);
 4. negative: light through the negative's dyes onto print paper (tungsten), the print's curves,
    printer filtration chosen so mid grey prints neutral at L* 50; slide: viewed directly;
 5. reflected/transmitted light under D50 -> XYZ -> sRGB (Bradford to D65), white = paper / clear film.
Writes a 33^3 .cube per film (Standard display -> film display) for GR Mod's Engine fit.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import colour
import numpy as np
from scipy.optimize import least_squares

WL = np.arange(380, 781, 5, dtype=float)
SHAPE = colour.SpectralShape(380, 780, 5)

FILMS = {
    # GR Mod film it is compared with: (negative or slide, print, scene illuminant, interlayer)
    "Portra 400": ("kodak_portra_400", "kodak_portra_endura", "D55", 0.30),
    "Gold 200": ("kodak_gold_200", "kodak_portra_endura", "D55", 0.30),
    "CineStill 800T": ("kodak_vision3_500t", "kodak_portra_endura", 4300, 0.30),  # tungsten film in mixed light, printed on paper
    "CineStill 800T (2383)": ("kodak_vision3_500t", "kodak_2383", 4300, 0.30),  # the same on cinema print film
    "Kodachrome 64": ("kodak_kodachrome_64", None, "D55", 0.20),
    "Velvia": ("fujifilm_velvia_100", None, "D55", 0.20),
    "Ektar 100": ("kodak_ektar_100", "kodak_portra_endura", "D55", 0.30),
    # each stock on the paper its profile names (Fujifilm on Crystal Archive)
    "Pro Neg Hi": ("fujifilm_pro_400h", "fujifilm_crystal_archive_typeii", "D55", 0.30),
    "Portra 160": ("kodak_portra_160", "kodak_portra_endura", "D55", 0.30),
    "Portra 800": ("kodak_portra_800", "kodak_portra_endura", "D55", 0.30),
    "Fujicolor C200": ("fujifilm_c200", "fujifilm_crystal_archive_typeii", "D55", 0.30),
    "Superia X-TRA 400": ("fujifilm_xtra_400", "fujifilm_crystal_archive_typeii", "D55", 0.30),
    "UltraMax 400": ("kodak_ultramax_400", "kodak_portra_endura", "D55", 0.30),
    # lab scans instead of optical prints (print = "scan"): what most film pictures seen today are
    "Portra 400 (scan)": ("kodak_portra_400", "scan", "D55", 0.30),
    "CineStill 800T (scan)": ("kodak_vision3_500t", "scan", 4300, 0.30),
}
# Lab auto-balance of a scan (1: the frame's grey made neutral; 0: balanced for the film's own light). A
# tungsten film in mixed light is only partly corrected by labs, which keeps CineStill's cool cast.
SCAN_BALANCE = {"CineStill 800T (scan)": 0.5}
SCAN_CONTRAST = 1.15  # labs add a little contrast to scans


def illuminant(name) -> np.ndarray:
    if isinstance(name, (int, float)):
        sd = colour.sd_blackbody(name, SHAPE)
    elif name == "T":
        sd = colour.sd_blackbody(3200, SHAPE)
    else:
        sd = colour.SDS_ILLUMINANTS[name].copy().align(SHAPE)
    v = sd.values
    return v / v[WL == 560][0]


def load(path: Path) -> dict:
    d = json.loads(path.read_text(encoding="utf-8"))
    x = d["data"]
    a = {k: np.array(x[k], dtype=float) for k in ("wavelengths", "log_sensitivity", "channel_density", "base_density", "log_exposure", "density_curves")}
    assert np.allclose(a["wavelengths"], WL)
    a["sens"] = np.nan_to_num(10 ** a["log_sensitivity"])
    a["dyes"] = np.nan_to_num(a["channel_density"])
    a["base"] = np.nan_to_num(a["base_density"])
    a["type"] = d["info"]["type"]
    a["ref"] = d["info"]["reference_illuminant"]
    return a


def density(stock: dict, log_e: np.ndarray) -> np.ndarray:
    return np.stack([np.interp(log_e[..., k], stock["log_exposure"], stock["density_curves"][:, k]) for k in range(3)], -1)


def interlayer(d: np.ndarray, amount: float) -> np.ndarray:
    return d + amount * (d - d.mean(-1, keepdims=True))


CMF = colour.MSDS_CMFS["CIE 1931 2 Degree Standard Observer"].copy().align(SHAPE).values
D50 = illuminant("D50")


def view(spectral_t: np.ndarray, white_t: np.ndarray) -> np.ndarray:
    """Transmission/reflectance spectra -> display sRGB, white = the given white spectrum."""
    xyz = (spectral_t * D50) @ CMF
    w = (white_t * D50) @ CMF
    xyz = xyz / w[1]
    wxy = colour.XYZ_to_xy(w / w[1])
    rgb = colour.XYZ_to_sRGB(xyz, illuminant=wxy, chromatic_adaptation_transform="Bradford")
    return np.clip(rgb, 0, 1)


def basis() -> np.ndarray:
    b = colour.recovery.MSDS_BASIS_FUNCTIONS_sRGB_MALLETT2019.copy().align(SHAPE).values  # (81, 3)
    return b


# Scanner channels: narrow bands at the dyes' peaks (red reads cyan dye, ...), as LED film scanners.
SCAN_BANDS = np.stack([np.exp(-0.5 * ((WL - c) / 15.0) ** 2) for c in (630, 540, 450)])


class Film:
    def __init__(self, neg: dict, prt: dict | str | None, scene, inter: float, mid: float = 0.18,
                 forward=None, balance: float = 1.0):
        self.neg, self.prt, self.inter, self.mid = neg, prt, inter, mid
        self.forward, self.balance = forward, balance
        light = illuminant(scene)
        self.m_ref = (neg["sens"] * illuminant(neg["ref"])[:, None]).T @ basis()
        # exposure of each layer for each sRGB basis primary: a 3x3 matrix (linear in the scene)
        self.m_neg = (neg["sens"] * light[:, None]).T @ basis()
        ref = illuminant("D55")
        grey = (neg["sens"] * ref[:, None]).T @ (basis() @ np.full(3, mid))
        self.offset = -np.log10(grey)  # mid grey under the reference light exposes logE = 0 on each layer
        self.lamp = illuminant("A")
        self.print_gain = np.zeros(3)
        self.exposure = np.zeros(3)
        self.calibrate()

    def negative(self, rgb: np.ndarray) -> np.ndarray:
        e = np.maximum(rgb @ self.m_neg.T, 1e-9)
        d = interlayer(density(self.neg, np.log10(e) + self.offset + self.exposure), self.inter)
        return 10 ** -(d @ self.neg["dyes"].T + self.neg["base"])

    def scan_density(self, rgb: np.ndarray, m=None) -> np.ndarray:
        if m is not None:
            keep, self.m_neg = self.m_neg, m
            t = self.negative(rgb)
            self.m_neg = keep
        else:
            t = self.negative(rgb)
        return -np.log10(np.maximum(t @ SCAN_BANDS.T / SCAN_BANDS.sum(1), 1e-12))

    def scan(self, rgb: np.ndarray) -> np.ndarray:
        """Lab scan: per-channel inversion of the negative's scanner densities (each channel's own
        gamma, so the straight part of the curves is equalised, as scanner software does), lab
        auto-balance, a little contrast, rendered through the camera's own Standard tone."""
        e = SCAN_CONTRAST * (self.scan_density(rgb) - self.d_mid) / self.gamma
        return self.forward(self.mid * 10 ** e)

    def __call__(self, rgb: np.ndarray) -> np.ndarray:
        if isinstance(self.prt, str):
            return self.scan(rgb)
        t = self.negative(rgb)
        if self.prt is None:
            white = 10 ** -(self.neg["base"])
            return view(t, white)
        p = self.prt
        e = np.maximum((t * self.lamp) @ p["sens"], 1e-12)
        d = density(p, np.log10(e) + self.print_gain)
        r = 10 ** -(d @ p["dyes"].T + p["base"])
        return view(r, 10 ** -p["base"])

    def calibrate(self) -> None:
        grey = np.full((1, 3), self.mid)
        target = np.array([50.0, 0.0, 0.0])

        def lab(rgb):
            return colour.XYZ_to_Lab(colour.sRGB_to_XYZ(rgb))[0]
        if isinstance(self.prt, str):
            step = 0.1  # log10 exposure
            lo = self.scan_density(grey * 10 ** -step)[0]; hi = self.scan_density(grey * 10 ** step)[0]
            self.gamma = (hi - lo) / (2 * step)
            d_scene = self.scan_density(grey)[0]
            d_ref = self.scan_density(grey, self.m_ref)[0]
            self.d_mid = self.balance * d_scene + (1 - self.balance) * d_ref
            return
        if self.prt is None:
            # slides: per-layer exposure (a camera colour-correction filter) so mid grey shows neutral at
            # L* 50. Without it Kodachrome came out blue at mid grey (b* -13): this simplified model has no
            # masking couplers, and Kodachrome is known as a warm film, not a blue one.
            def f(v):
                self.exposure = v
                return lab(self(grey)) - target
            least_squares(f, np.zeros(3), x_scale=0.1)
        else:
            def f(v):
                self.print_gain = v
                return lab(self(grey)) - target
            least_squares(f, np.full(3, -float(np.log10(np.maximum((self.negative(grey) * self.lamp) @ self.prt["sens"], 1e-12)).mean())), x_scale=0.1)


def standard_inverse(theta: np.ndarray):
    """Standard display -> scene linear sRGB (LibRaw camera-WB space), inverting the calibrated model."""
    k = 22
    knots = np.linspace(-13.0, 2.5, k)
    m = theta[:9].reshape(3, 3)
    cv = theta[9:9 + 3 * k].reshape(3, k)
    vals = (np.cumsum(np.log1p(np.exp(cv)), axis=1) - np.log1p(np.exp(cv[:, :1]))) / 30.0
    minv = np.linalg.inv(m)
    gain = 0.6  # median exposure gain of the user's Standard pairs

    def inv(display: np.ndarray) -> np.ndarray:
        x = np.stack([2 ** np.interp(np.clip(display[..., c], vals[c, 0], vals[c, -1]), vals[c], knots) for c in range(3)], -1)
        return np.maximum(x @ minv.T / gain, 0)
    return inv


def standard_forward(theta: np.ndarray):
    """Scene linear sRGB -> Standard display: the calibrated model forward (inverse of standard_inverse)."""
    k = 22
    knots = np.linspace(-13.0, 2.5, k)
    m = theta[:9].reshape(3, 3)
    cv = theta[9:9 + 3 * k].reshape(3, k)
    vals = (np.cumsum(np.log1p(np.exp(cv)), axis=1) - np.log1p(np.exp(cv[:, :1]))) / 30.0
    gain = 0.6

    def fwd(lin: np.ndarray) -> np.ndarray:
        x = np.log2(np.maximum((lin * gain) @ m.T, 2 ** -13.0))
        return np.clip(np.stack([np.interp(x[..., c], knots, vals[c]) for c in range(3)], -1), 0, 1)
    return fwd


def cube_text(title: str, lut: np.ndarray) -> str:
    n = lut.shape[0]
    lines = [f'TITLE "{title}"', f"LUT_3D_SIZE {n}", "DOMAIN_MIN 0 0 0", "DOMAIN_MAX 1 1 1"]
    for b in range(n):
        for g in range(n):
            for r in range(n):
                lines.append("%.6f %.6f %.6f" % tuple(lut[r, g, b]))
    return "\n".join(lines) + "\n"


def main() -> None:
    profiles, theta_path, out = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
    out.mkdir(parents=True, exist_ok=True)
    theta = np.load(theta_path)
    inv, fwd = standard_inverse(theta), standard_forward(theta)
    n = 33
    axis = np.linspace(0, 1, n)
    grid = np.stack(np.meshgrid(axis, axis, axis, indexing="ij"), -1)
    scene = inv(grid.reshape(-1, 3))
    # Anchor exposure on the camera's own mid grey: the scene value Standard shows at L* 50 stays at L* 50
    # on film (a first version anchored a nominal 0.18 and made the slide films far too dense).
    mid = float(inv(np.full((1, 3), colour.XYZ_to_sRGB(colour.Lab_to_XYZ([50.0, 0, 0]))[1]))[0].mean())
    print("Standard mid grey (L* 50) = scene", round(mid, 4))
    report = {}
    for name, (neg, prt, light, inter) in FILMS.items():
        paper = prt if prt == "scan" else (load(profiles / f"{prt}.json") if prt else None)
        film = Film(load(profiles / f"{neg}.json"), paper, light, inter, mid, fwd, SCAN_BALANCE.get(name, 1.0))
        lut = film(scene).reshape(n, n, n, 3)
        stem = neg + ("-" + prt if prt else "")
        (out / f"{stem}.cube").write_text(cube_text(f"{name} (datasheet)", lut), encoding="utf-8")
        ramp = np.linspace(0.005, 1.6, 9)[:, None] * np.ones(3)
        lab = colour.XYZ_to_Lab(colour.sRGB_to_XYZ(film(ramp * mid / 0.18)))
        report[name] = {"negative": neg, "print": prt, "sceneLight": light, "interlayer": inter,
                        "greyRampLab": np.round(lab, 1).tolist(), "printGain": np.round(film.print_gain, 3).tolist(), "exposure": np.round(film.exposure, 3).tolist()}
        print(name, "grey ramp L*a*b*:", np.round(lab[:, 0], 1).tolist(), "a:", np.round(lab[:, 1], 1).tolist(), "b:", np.round(lab[:, 2], 1).tolist())
    (out / "datasheet-report.json").write_text(json.dumps(report, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
