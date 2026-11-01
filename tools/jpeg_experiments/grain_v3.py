"""Film grain: GR Mod's current camera grain against a physical reference and a camera-feasible proposal.

    python grain_v3.py COMPARE_DIR

 - current: core/src/color/grain.ts (grainY) ported to numpy: value noise on a 1.25 / 2.25 px lattice,
   bilinear, luma only, scaled by a brightness bell.
 - reference: the Boolean film grain model (Newson, Faraj, Galerne, Delon, "Realistic Film Grain
   Rendering", IPOL 2017): per dye layer, discs with log-normal radii at Poisson intensity
   lambda = ln(1 / (1 - u)) / (pi E[r^2]), u the layer's coverage (1 - linear light), rendered 4x
   supersampled, box-averaged to pixels and blurred (enlarger/scan, sigma 0.5 px). Layers are partly
   correlated (dye clouds form largely independently per layer; most of what a print shows is luminous).
 - proposed: what the camera module could do cheaply, in the manner of AV1's film grain synthesis: a
   256 x 256 grain tile (luma, plus Cb/Cr at half horizontal resolution as in 4:2:2) generated offline
   from the reference model, laid over the picture in 64-pixel blocks at random offsets with
   variance-preserving cross-fades, scaled by a brightness table measured on the reference. Per pixel,
   a table lookup and a multiply.
All three are calibrated to the same luma RMS at mid grey, so they differ in structure, distribution
over tones and colour, not in overall amount.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

FULL_WIDTH = 6000
# Coverage cap of the Boolean model (bounds the disc count). 0.985 left visible noise in deep shadows:
# the capped layer's variance was added to the true, darker value and amplified by the display curve.
CAP = 0.999


# ---------------------------------------------------------------- colour helpers
def lin(x):
    return np.where(x <= 0.04045, x / 12.92, ((x + 0.055) / 1.055) ** 2.4)


def enc(x):
    x = np.clip(x, 0, 1)
    return np.where(x <= 0.0031308, 12.92 * x, 1.055 * x ** (1 / 2.4) - 0.055)


def to_ycc(rgb):
    """JPEG (BT.601 full range) in 0..255 units."""
    r, g, b = rgb[..., 0] * 255, rgb[..., 1] * 255, rgb[..., 2] * 255
    y = 0.299 * r + 0.587 * g + 0.114 * b
    return y, -0.168736 * r - 0.331264 * g + 0.5 * b, 0.5 * r - 0.418688 * g - 0.081312 * b


def from_ycc(y, cb, cr):
    r = y + 1.402 * cr
    g = y - 0.344136 * cb - 0.714136 * cr
    b = y + 1.772 * cb
    return np.clip(np.stack([r, g, b], -1) / 255, 0, 1)


# ---------------------------------------------------------------- current GR Mod grain (grain.ts)
AMOUNT = [9, 15, 24]
CELL = [320, 576]


def grain_tone():
    out = np.zeros((3, 256))
    for a, spread in enumerate([0.7, 0.62, 0.5]):
        u = (np.arange(256) / 255) ** 0.8
        out[a] = np.round(255 * np.maximum(0, np.sin(np.pi * u)) ** spread)
    return out


def _hash(i, j, seed):
    i = i.astype(np.uint32); j = j.astype(np.uint32)
    h = (i * np.uint32(0x9E3779B1)) ^ (j * np.uint32(0x85EBCA77)) ^ np.uint32(seed)
    h ^= h >> np.uint32(15); h *= np.uint32(0x2C1B3C6D); h ^= h >> np.uint32(12); h *= np.uint32(0x297A2D39); h ^= h >> np.uint32(15)
    return (h & 0xFF).astype(np.int32) + ((h >> 8) & 0xFF).astype(np.int32) - 255


def current_grain(rgb, amount, size, seed=12345, x0=0, y0=0):
    """grainY on the luma of a crop at its position (x0, y0) in a 6000-wide picture."""
    y, cb, cr = to_ycc(rgb)
    Y = np.clip(np.round(y), 0, 255).astype(np.int32)
    h, w = Y.shape
    cell = CELL[size]
    gain = AMOUNT[amount - 1]
    step = (256 << 16) // cell
    xs = (np.arange(w) + x0) * step; ys = (np.arange(h) + y0) * step
    li, fx = xs >> 16, (xs >> 8) & 255
    lj, fy = ys >> 16, (ys >> 8) & 255
    J, I = np.meshgrid(np.arange(lj.min(), lj.max() + 2), np.arange(li.min(), li.max() + 2), indexing="ij")
    lat = _hash(I, J, seed)
    j0, i0 = lj - lj.min(), li - li.min()
    a = lat[j0][:, i0]; b = lat[j0][:, i0 + 1]; c = lat[j0 + 1][:, i0]; d = lat[j0 + 1][:, i0 + 1]
    mix0 = a * 256 + (c - a) * fy[:, None]
    mix1 = b * 256 + (d - b) * fy[:, None]
    v = (mix0 * (256 - fx[None, :]) + mix1 * fx[None, :]) >> 16
    t = grain_tone()[amount - 1][Y].astype(np.int64)
    Y2 = np.clip(Y + ((v * gain * t) >> 16), 0, 255)
    return from_ycc(Y2.astype(float), cb, cr)


# ---------------------------------------------------------------- Boolean model reference
def boolean_layer(u, r_mean, r_rel, rng, ss=4, blur=0.5):
    """Coverage (0..1) of one layer rendered with the inhomogeneous Boolean model."""
    h, w = u.shape
    sig = np.sqrt(np.log(1 + r_rel ** 2)); mu = np.log(r_mean) - sig ** 2 / 2
    er2 = r_mean ** 2 * (1 + r_rel ** 2)
    lam = -np.log(1 - np.clip(u, 0, CAP)) / (np.pi * er2)
    counts = rng.poisson(lam).ravel()
    idx = np.repeat(np.arange(h * w), counts)
    cy = (idx // w + rng.random(idx.size)) * ss
    cx = (idx % w + rng.random(idx.size)) * ss
    rad = np.exp(rng.normal(mu, sig, idx.size)) * ss
    grid = np.zeros((h * ss + 64, w * ss + 64), bool)
    pad = 32
    rq = np.clip(np.round(rad * 2) / 2, 0.5, 30)
    for R in np.unique(rq):
        sel = rq == R
        n = int(np.ceil(R))
        dy, dx = np.mgrid[-n:n + 1, -n:n + 1]
        keep = dy ** 2 + dx ** 2 <= R * R
        dy, dx = dy[keep], dx[keep]
        py = np.floor(cy[sel]).astype(np.int64) + pad; px = np.floor(cx[sel]).astype(np.int64) + pad
        for k in range(0, py.size, 200_000):
            grid[(py[k:k + 200_000, None] + dy[None]).ravel(), (px[k:k + 200_000, None] + dx[None]).ravel()] = True
    cov = grid[pad:pad + h * ss, pad:pad + w * ss].reshape(h, ss, w, ss).mean((1, 3))
    return ndimage.gaussian_filter(cov, blur)


def mix_layers(res, a, cloud=0.8):
    """Correlate the layers' grain: the common (luminous) part stays sharp; each layer's own part is
    softened into dye clouds (sigma `cloud` px; a first version left it sharp and the shadows sparkled
    with single green/magenta pixels, like digital chroma noise) and weighted 1 - a. Variance kept."""
    m = res.mean(-1, keepdims=True)
    own = res - m
    if cloud:
        soft = np.stack([ndimage.gaussian_filter(own[..., c], cloud) for c in range(3)], -1)
        own = soft * (own.std() / max(soft.std(), 1e-9))
    out = m + (1 - a) * own
    return out * (res.std() / max(out.std(), 1e-9))


def reference_grain(rgb, r_mean, k=1.0, a=0.65, seed=1):
    rng = np.random.default_rng(seed)
    u = 1 - lin(rgb)
    cov = np.stack([boolean_layer(u[..., c], r_mean, 0.4, rng) for c in range(3)], -1)
    # the grain is the coverage minus its expectation; the expectation of the rendered layer is the
    # capped coverage (boolean_layer caps u at CAP to bound the number of discs). Subtracting the
    # uncapped u instead brightened the deep shadows (a lifted black, not grain): a first run's bug.
    expect = np.stack([ndimage.gaussian_filter(np.clip(u[..., c], 0, CAP), 0.5) for c in range(3)], -1)
    res = mix_layers(cov - expect, a)
    return enc(1 - np.clip(u + k * res, 0, 1))


# ---------------------------------------------------------------- camera-feasible proposal
def make_tile(r_mean, a=0.65, n=256, seed=7):
    """Grain tile from the reference on a flat mid-grey field: luma, Cb, Cr (unit luma std)."""
    rng = np.random.default_rng(seed)
    flat = np.full((n + 32, n + 32), 0.5)
    cov = np.stack([boolean_layer(flat, r_mean, 0.4, rng) for _ in range(3)], -1)[16:-16, 16:-16]
    res = mix_layers(cov - cov.mean((0, 1)), a)
    # display-domain grain direction (darkness -> brightness), in YCbCr units
    y, cb, cr = to_ycc(-res)
    s = y.std()
    # Cb, Cr at half horizontal resolution (4:2:2), as the module would store them
    cb2 = cb.reshape(n, n // 2, 2).mean(-1); cr2 = cr.reshape(n, n // 2, 2).mean(-1)
    return y / s, cb2 / s, cr2 / s


def amplitude_table(r_mean, a=0.65):
    """Luma grain RMS of the reference by display brightness (flat fields), 0..255 units."""
    rng = np.random.default_rng(3)
    levels = np.linspace(0.02, 0.98, 25)
    rms = []
    for L in levels:
        flat = np.full((96, 96, 3), L)
        u = 1 - lin(flat)
        cov = np.stack([boolean_layer(u[..., c], r_mean, 0.4, rng) for c in range(3)], -1)
        out = enc(1 - np.clip(u.mean() + mix_layers(cov - cov.mean((0, 1)), a), 0, 1))
        rms.append(to_ycc(out)[0][8:-8, 8:-8].std())
    return np.interp(np.arange(256), levels * 255, rms)


def tile_field(tile, h, w, rng, block=64, fade=8):
    """Lay a tile over h x w in blocks at random offsets, variance-preserving cross-fades."""
    n0, n1 = tile.shape
    out = np.zeros((h, w)); wsum = np.zeros((h, w))
    for by in range(-fade, h, block):
        for bx in range(-fade, w, block):
            oy, ox = rng.integers(0, n0 - block - 2 * fade), rng.integers(0, n1 - block - 2 * fade)
            hh, ww = block + 2 * fade, block + 2 * fade
            patch = tile[oy:oy + hh, ox:ox + ww]
            ramp_y = np.clip(np.minimum(np.arange(hh) + 1, hh - np.arange(hh)) / (2 * fade), 0, 1)
            ramp_x = np.clip(np.minimum(np.arange(ww) + 1, ww - np.arange(ww)) / (2 * fade), 0, 1)
            wgt = ramp_y[:, None] * ramp_x[None, :]
            y0, x0 = by, bx
            ys, xs = slice(max(0, y0), min(h, y0 + hh)), slice(max(0, x0), min(w, x0 + ww))
            py, px = slice(ys.start - y0, ys.stop - y0), slice(xs.start - x0, xs.stop - x0)
            out[ys, xs] += patch[py, px] * wgt[py, px]
            wsum[ys, xs] += wgt[py, px] ** 2
    return out / np.sqrt(np.maximum(wsum, 1e-6))


def proposed_grain(rgb, tiles, table, k=1.0, seed=5):
    """table: relative strength by brightness (1 at mid grey); k: luma RMS at mid grey."""
    rng = np.random.default_rng(seed)
    ty, tcb, tcr = tiles
    y, cb, cr = to_ycc(rgb)
    h, w = y.shape
    gy = tile_field(ty, h, w, rng)
    # chroma tiles are half width: lay them at half width and repeat (what 4:2:2 stores)
    gcb = np.repeat(tile_field(tcb, h, (w + 1) // 2, rng), 2, 1)[:, :w]
    gcr = np.repeat(tile_field(tcr, h, (w + 1) // 2, rng), 2, 1)[:, :w]
    amp = k * table[np.clip(np.round(y), 0, 255).astype(int)]
    return from_ycc(y + amp * gy, cb + amp * gcb, cr + amp * gcr)


# ---------------------------------------------------------------- measurement
def radial_psd(res):
    f = np.abs(np.fft.fftshift(np.fft.fft2(res - res.mean()))) ** 2
    h, w = res.shape
    yy, xx = np.indices((h, w)); r = np.hypot(yy - h // 2, xx - w // 2) / max(h, w)
    bins = np.linspace(0, 0.5, 21)
    p = np.array([f[(r >= bins[i]) & (r < bins[i + 1])].mean() for i in range(20)])
    return p / p.sum()


def fit_table(r, samples):
    """The camera table: luma grain RMS by brightness, measured on the reference over real pictures
    (normalised to 1 at mid grey)."""
    edges = np.linspace(0, 256, 17)
    acc = np.zeros(16); cnt = np.zeros(16)
    # measured at a realistic amplitude (3 levels RMS at mid grey): at the model's raw amplitude (about 50)
    # shadows and highlights clip at 0 and 255 and their RMS collapses (a first version's mistake)
    flat = reference_grain(np.full((192, 192, 3), 0.5), r, 1.0)
    k = 3.0 / to_ycc(flat)[0][8:-8, 8:-8].std()
    for img in samples:
        ref = reference_grain(img, r, k, seed=11)
        yb = to_ycc(img)[0]; res = to_ycc(ref)[0] - yb
        b = np.clip(np.digitize(yb, edges) - 1, 0, 15)
        for i in range(16):
            m = b == i
            acc[i] += (res[m] ** 2).sum(); cnt[i] += m.sum()
    ok = cnt > 2000
    centres = (edges[:-1] + edges[1:]) / 2
    rms = np.sqrt(acc[ok] / cnt[ok])
    shape = np.interp(np.arange(256), np.concatenate([[0], centres[ok], [255]]), np.concatenate([[rms[0] * 0.8], rms, [0]]))
    shape = ndimage.gaussian_filter1d(shape, 6)
    rel = rms / np.interp(128, centres[ok], rms)
    return shape / shape[128], {int(c): round(float(v), 3) for c, v in zip(centres[ok], rel)}


def main():
    d = Path(sys.argv[1])
    out = d / "story"
    data = json.loads((d / "data.js").read_text(encoding="utf-8").split("=", 1)[1].rstrip().rstrip(";"))
    n = data["grid"]
    sys.path.insert(0, str(Path(__file__).parent))
    from compare_page_v3 import apply_grid
    from PIL import ImageOps

    def grid(film, variant):
        m = next(x for x in data["models"] if x["film"] == film and x["variant"] == variant)
        return np.frombuffer((d / "models" / f"{m['file']}-native.f32").read_bytes(), dtype="<f4").reshape(n, n, n, 3)

    # (photo, crop centre as fraction, film, variant, GR Mod grain setting amount/size)
    cases = [
        ("R0000030", (0.42, 0.40), "Portra 400", "film", (1, 0)),
        ("R0000022", (0.30, 0.18), "Portra 400", "film", (1, 0)),
        ("AK000164", (0.38, 0.42), "CineStill 800T", "film", (2, 1)),
        ("R0000013", (0.55, 0.55), "Gold 200", "current", (2, 0)),
    ]
    radius = {0: 0.55, 1: 1.3}  # small / large grain: disc radius in pixels of a 6000-wide picture
    # tables from the reference over varied real content (page photos, 512 px crops)
    samples = []
    for pid in ["Ricoh-R0000027", "Ricoh-R0000030", "Ricoh-AK000164", "Ricoh2-AK000008", "Ricoh-R0000013", "Ricoh2-AK000016"]:
        im = np.asarray(Image.open(d / "photos" / f"{pid}.jpg"), dtype=np.float64) / 255
        h, w = im.shape[:2]
        samples.append(im[(h - 512) // 2:(h + 512) // 2, (w - 512) // 2:(w + 512) // 2])
    tables, tiles, shapes = {}, {}, {}
    for size, r in radius.items():
        tables[size], shapes[size] = fit_table(r, samples)
        tiles[size] = make_tile(r)
        print("tone table", "small" if size == 0 else "large", shapes[size], flush=True)
    report = {"radius": radius, "toneTables": {("small" if k == 0 else "large"): v for k, v in shapes.items()}, "cases": {}}
    for photo, (fx, fy), film, variant, (amount, size) in cases:
        src = ImageOps.exif_transpose(Image.open(rf"C:\Users\Antoine\Pictures\Ricoh\{photo}.JPG")).convert("RGB")
        W, H = src.size
        cw = 640
        x0 = int(np.clip(fx * W - cw / 2, 0, W - cw)); y0 = int(np.clip(fy * H - cw / 2, 0, H - cw))
        crop = np.asarray(src.crop((x0, y0, x0 + cw, y0 + cw)), dtype=np.float64) / 255
        base = apply_grid(crop, grid(film, variant))
        r = radius[size]
        cur = current_grain(base, amount, size, x0=x0, y0=y0)
        rms_cur = to_ycc(current_grain(np.full((256, 256, 3), 0.5), amount, size))[0].std()
        ref_flat = reference_grain(np.full((192, 192, 3), 0.5), r, 1.0)
        k_ref = rms_cur / to_ycc(ref_flat)[0][8:-8, 8:-8].std()
        ref = reference_grain(base, r, k_ref)
        prop = proposed_grain(base, tiles[size], tables[size], rms_cur)
        name = f"grain-{photo}"
        for tag, img in [("none", base), ("current", cur), ("reference", ref), ("proposed", prop)]:
            Image.fromarray((np.clip(img, 0, 1) * 255 + .5).astype(np.uint8)).save(out / f"{name}-{tag}.png")
        yb, cbb, crb = to_ycc(base)
        rec = {"film": film, "variant": variant, "setting": [amount, size], "radiusPx": r, "crop": [x0, y0, cw]}
        for tag, img in [("current", cur), ("reference", ref), ("proposed", prop)]:
            yg, cbg, crg = to_ycc(img)
            res = yg - yb
            cres = np.hypot(cbg - cbb, crg - crb)
            bands = {}
            for lo, hi, lab in [(0, 40, "shadows"), (40, 110, "lowMid"), (110, 180, "highMid"), (180, 240, "highlights")]:
                m = (yb >= lo) & (yb < hi)
                bands[lab] = round(float(res[m].std()), 2) if m.sum() > 500 else None
            rec[tag] = {"lumaRms": round(float(res.std()), 2), "chromaRms": round(float(cres.std()), 2), "byTone": bands,
                        "psd": np.round(radial_psd(res), 4).tolist()}
        report["cases"][photo] = rec
        print(photo, film, {t: (rec[t]["lumaRms"], rec[t]["chromaRms"], rec[t]["byTone"]) for t in ("current", "reference", "proposed")}, flush=True)
    (out / "grain.json").write_text(json.dumps(report, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
