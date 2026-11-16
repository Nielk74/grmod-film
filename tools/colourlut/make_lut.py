# SPDX-License-Identifier: GPL-2.0-only
"""Make a film's "full look" colour LUT: camera today -> the film's authored cube, as 33^3 Q4 deltas (dY, dCb, dCr).

The LUT's input is what the camera produces today for the film (its fitted matrix, curves and post matrix); its target is the film's
authored look, the film's .cube applied to the Standard rendering. For each node of the camera's YCbCr grid (nodes clipped into gamut, as
tools/colour_engine/engine.py build_lut does):
  1. the node's RGB is what the camera must have produced; the Standard colour that gives it is found by inverting a float version of
     the camera model (common.camera_today: Sinv, 3x3, clip, S tone curve, per-channel curve, post matrix) with damped Gauss-Newton;
  2. the cube is applied to that Standard colour (trilinear, float);
  3. the delta is the target's YCbCr minus the node's (BT.601 full range), x16, rounded to int16.
Nodes the camera cannot produce (residual above RESIDUAL_MAX levels) get the diffusion of their reachable neighbours' deltas
(a Laplace fill: smooth continuation, no noise). The grey axis is NOT forced neutral: the target's tinted blacks and whites are the look.

    python tools/colourlut/make_lut.py "Classic Neg" "Classic Chrome" "Blockbuster"

Writes scratch/colour-engine/lut-<film>-full.npy (the folder of the prototype: GRMOD_COLOUR_SCRATCH) and prints the worst residuals.
Needs numpy and Pillow, and the prototype (tools/colour_engine, GRMOD_COLOUR_ENGINE_DIR) for its colour helpers and coefficients.
"""
import json
import os
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]


def search(env, *rel):
    cands = ([Path(os.environ[env])] if os.environ.get(env) else []) + [base / Path(*rel) for base in (ROOT, *ROOT.parents)]
    for c in cands:
        if c.exists():
            return c
    sys.exit(f'{Path(*rel)} not found ({env})')


ENGINE_DIR = search('GRMOD_COLOUR_ENGINE_DIR', 'tools', 'colour_engine')
SCRATCH = search('GRMOD_COLOUR_SCRATCH', 'scratch', 'colour-engine')
sys.path.insert(0, str(ENGINE_DIR))
import common  # noqa: E402
import engine  # noqa: E402

CUBES = SCRATCH.parent.parent / 'examples' / 'gr3x' / 'film-pack-v3' / 'out' / 'cube'
if not CUBES.exists():
    CUBES = search('GRMOD_FILM_CUBES', 'examples', 'gr3x', 'film-pack-v3', 'out', 'cube')
RESIDUAL_MAX = 1.5          # levels (0..255): beyond it a node is "not producible"
N = 33
SLUG = {'Classic Neg': 'classic-neg', 'Classic Chrome': 'classic-chrome', 'Blockbuster': 'blockbuster'}


def load_coef():
    c = json.load(open(SCRATCH / 'coef-all.json', encoding='utf-8'))
    common._coef = c
    return c


def read_cube(path):
    with open(path, encoding='utf-8') as fh:
        rows = [ln.split() for ln in fh if ln.strip() and (ln[0].isdigit() or ln[0] == '-')]
    n = round(len(rows) ** (1 / 3))
    return np.array(rows, np.float64).reshape(n, n, n, 3)  # [b][g][r]


def apply_cube_float(rgb, cube):
    """rgb: (..., 3) floats 0..255 -> floats 0..255 (trilinear, as gap_report.apply_cube without rounding)."""
    n = cube.shape[0]
    p = np.clip(rgb, 0, 255) / 255 * (n - 1)
    i = np.clip(p.astype(np.int32), 0, n - 2)
    f = p - i
    out = 0.0
    for db in (0, 1):
        for dg in (0, 1):
            for dr in (0, 1):
                w = (f[..., 2] if db else 1 - f[..., 2]) * (f[..., 1] if dg else 1 - f[..., 1]) * (f[..., 0] if dr else 1 - f[..., 0])
                out = out + w[..., None] * cube[i[..., 2] + db, i[..., 1] + dg, i[..., 0] + dr]
    return np.clip(out, 0, 1) * 255


class Model:
    """The float camera model of common.camera_today (no rounding), for a film."""

    def __init__(self, coef, film):
        c = coef
        self.Sinv = np.array(c['Sinv'], np.float64)
        self.S = np.array(c['S'], np.float64)
        std = np.array(c['standardQ13'], np.float64).reshape(3, 3) / 8192
        f = c[film]
        self.M = (np.array(f['matrixQ13'], np.float64).reshape(3, 3) / 8192) @ np.linalg.inv(std)
        self.curves = [np.array(k, np.float64) for k in f['curves']]
        self.post = np.array(f['postQ9'], np.float64).reshape(3, 3) / 512 if f['postQ9'] else np.eye(3)

    def __call__(self, s):
        """s: (n, 3) Standard sRGB 0..255 -> camera RGB 0..255 (float)."""
        lin = np.interp(s, np.arange(256), self.Sinv)
        cv = []
        for ch in range(3):
            l = np.clip(lin @ self.M[ch], 0, 1)
            d = np.interp(l * 4096, np.arange(4097), self.S)
            pos = np.clip(d * 16383 / 64, 0, 255)
            cv.append(np.interp(pos, np.arange(256), self.curves[ch]) / 16383)
        cv = np.stack(cv, -1)
        return np.clip(cv @ self.post.T, 0, 1) * 255


def closed_form(model, target):
    """The inverse of the model chain ignoring the clips (monotone envelopes of the tables): a second starting point for the solver."""
    cv = np.clip(target / 255 @ np.linalg.inv(model.post).T, 0, 1)
    l = np.empty_like(cv)
    for ch in range(3):
        curve = np.maximum.accumulate(model.curves[ch])
        pos = np.interp(cv[:, ch] * 16383, curve, np.arange(256))
        d = pos * 64 / 16383
        l[:, ch] = np.interp(d, np.maximum.accumulate(model.S), np.arange(4097)) / 4096
    lin = np.clip(l @ np.linalg.inv(model.M).T, 0, 1)
    return np.interp(lin, np.maximum.accumulate(model.Sinv), np.arange(256))


def invert(model, target, iters=80):
    """Standard colours s (n, 3) with model(s) = target (n, 3): damped Gauss-Newton from two starting points (the target itself and the
    clip-free closed-form inverse), the better kept. Returns s and the residual per node."""
    a, ra = _solve(model, target, target.copy(), iters)
    b, rb = _solve(model, target, closed_form(model, target), iters)
    # Where the model is not one-to-one (clipped channels) several Standard colours give the node: keep the one nearest to the node
    # (the smallest change), not whichever the solver found last. Above the tolerance, the better fit wins.
    tol = 0.3
    near_a, near_b = np.linalg.norm(a - target, axis=-1), np.linalg.norm(b - target, axis=-1)
    use = np.where((ra < tol) & (rb < tol), near_b < near_a, rb < ra)
    return np.where(use[:, None], b, a), np.where(use, rb, ra)


def _solve(model, target, s, iters):
    lam = np.full(len(s), 1.0)
    r = model(s) - target
    e = (r ** 2).sum(-1)
    eye = np.eye(3)
    for _ in range(iters):
        J = np.empty((len(s), 3, 3))
        for k in range(3):
            d = np.zeros(3)
            d[k] = 1.0
            J[:, :, k] = (model(np.clip(s + d, 0, 255)) - model(np.clip(s - d, 0, 255))) / (np.clip(s + d, 0, 255)[:, k] - np.clip(s - d, 0, 255)[:, k])[:, None].clip(1e-9)
        A = np.einsum('nij,nik->njk', J, J) + lam[:, None, None] * eye
        g = np.einsum('nij,ni->nj', J, r)
        step = np.linalg.solve(A, -g[..., None])[..., 0]
        s2 = np.clip(s + step, 0, 255)
        r2 = model(s2) - target
        e2 = (r2 ** 2).sum(-1)
        better = e2 < e
        s = np.where(better[:, None], s2, s)
        r = np.where(better[:, None], r2, r)
        e = np.where(better, e2, e)
        lam = np.where(better, np.maximum(lam * 0.5, 1e-3), np.minimum(lam * 4, 1e6))
    return s, np.sqrt(e)


def laplace_fill(d, fixed, passes=2000):
    """Fill d (N,N,N,3) where ~fixed with the diffusion of the fixed values (edge-replicated neighbours)."""
    d = d.copy()
    d[~fixed] = d[fixed].mean(0) if fixed.any() else 0
    free = ~fixed
    for _ in range(passes):
        p = np.pad(d, [(1, 1), (1, 1), (1, 1), (0, 0)], mode='edge')
        m = (p[:-2, 1:-1, 1:-1] + p[2:, 1:-1, 1:-1] + p[1:-1, :-2, 1:-1] + p[1:-1, 2:, 1:-1] + p[1:-1, 1:-1, :-2] + p[1:-1, 1:-1, 2:]) / 6
        d = np.where(free[..., None], m, d)
    return d


def tetra(v):
    """The camera's tetrahedral lookup as sparse weights for float lookup points v (n, 3) in 0..255: node indices (n, 4) and weights (n, 4)."""
    node = np.minimum((v // 8).astype(np.int64), N - 2) if False else np.minimum(np.floor(v / 8).astype(np.int64), 31)
    f = (v - node * 8) / 8
    order = np.argsort(-f, axis=1, kind='stable')
    fs = np.take_along_axis(f, order, 1)
    steps = np.array([N * N, N, 1])
    base = node[:, 0] * N * N + node[:, 1] * N + node[:, 2]
    idx = np.empty((len(v), 4), np.int64)
    idx[:, 0] = base
    cum = base.copy()
    for k in range(3):
        cum = cum + steps[order[:, k]]
        idx[:, k + 1] = cum
    w = np.stack([1 - fs[:, 0], fs[:, 0] - fs[:, 1], fs[:, 1] - fs[:, 2], fs[:, 2]], 1)
    return idx, w


def fit(idx, w, sw, delta, lam, iters=200):
    """Least squares for the table x (N^3, 3): min sum sw |A x - delta|^2 + lam sum |differences between neighbouring nodes|^2, by CG on the normal equations."""
    n = N ** 3
    shape = (N, N, N, 3)

    def A_T_A(x):
        out = np.zeros((n, 3))
        pred = (x[idx] * w[..., None]).sum(1)
        r = pred * sw[:, None]
        for k in range(4):
            for c in range(3):
                out[:, c] += np.bincount(idx[:, k], weights=r[:, c] * w[:, k], minlength=n)
        g = x.reshape(shape)
        for ax in range(3):
            d = np.diff(g, axis=ax)
            t = np.zeros(shape)
            lo = [slice(None)] * 4; hi = [slice(None)] * 4
            lo[ax] = slice(0, N - 1); hi[ax] = slice(1, N)
            t[tuple(lo)] -= d; t[tuple(hi)] += d
            out += lam * t.reshape(n, 3)
        return out

    rhs = np.zeros((n, 3))
    r0 = delta * sw[:, None]
    for k in range(4):
        for c in range(3):
            rhs[:, c] += np.bincount(idx[:, k], weights=r0[:, c] * w[:, k], minlength=n)
    x = np.zeros((n, 3)); r = rhs - A_T_A(x); p = r.copy(); rs = (r * r).sum()
    for _ in range(iters):
        Ap = A_T_A(p)
        a = rs / (p * Ap).sum()
        x += a * p; r -= a * Ap
        rn = (r * r).sum()
        if rn < 1e-10 * (rhs * rhs).sum():
            break
        p = r + (rn / rs) * p; rs = rn
    return x.reshape(shape)


# (smoothness lambda, weight of the near-neutral light colours) per film, tuned on the real photos for the gap to the target against blotchy
# colour in clouds and sky (a low lambda follows the target closely but amplifies chroma noise; Classic Neg's steep field needs the most smoothing)
PARAMS = {'Classic Neg': (30.0, 3.0), 'Classic Chrome': (20.0, 3.0), 'Blockbuster': (20.0, 3.0)}
LAMBDA = 20.0
WHITE_BOOST = 3.0
STEP = 3          # Standard colours sampled every STEP levels (plus the grey ramp, every level)


def make(film, coef, lam=None):
    if lam is None:
        lam, wb = PARAMS.get(film, (LAMBDA, WHITE_BOOST))
        globals()['WHITE_BOOST'] = wb
    model = Model(coef, film)
    cube = read_cube(CUBES / coef[film]['cube'])
    g = np.minimum(np.arange(N) * engine.STEP, 255).astype(np.float64)
    Yg, Cbg, Crg = np.meshgrid(g, g, g, indexing='ij')
    ycc = np.stack([Yg, Cbg, Crg], -1).reshape(-1, 3)
    node = np.clip(engine.ycc_to_rgb(ycc), 0, 255)
    # 1. node by node: the Standard colour whose camera output is the node (residual report; the producible region)
    s, res = invert(model, node)
    ok = (res < RESIDUAL_MAX)
    # 2. the table: least squares over the Standard colours, on the camera's own tetrahedral interpolation. Each sample is a Standard colour:
    #    where the camera puts it (YCbCr) and how far the target is from that. Nodes no sample reaches are filled smoothly by the
    #    neighbour differences term (a Laplace fill); the grey axis is not forced neutral (tinted blacks and whites are the look).
    v = np.arange(0, 256, STEP, dtype=np.float64)
    grid = np.stack(np.meshgrid(v, v, v, indexing='ij'), -1).reshape(-1, 3)
    ramp = np.repeat(np.arange(256, dtype=np.float64)[:, None], 3, 1)
    std = np.concatenate([grid, ramp])
    cam = model(std)
    pos = np.clip(engine.rgb_to_ycc(cam), 0, 255)
    delta = engine.rgb_to_ycc(apply_cube_float(std, cube)) - engine.rgb_to_ycc(cam)
    lab = common.srgb_to_oklab(std / 255.0)
    chroma = np.hypot(lab[:, 1], lab[:, 2])
    sw = np.sqrt(1.0 / (1.0 + chroma / 0.15))
    sw[len(grid):] *= 3.0       # the grey ramp counts more: greys and whites must stay right
    sw[(chroma < 0.05) & (lab[:, 0] > 0.75)] *= WHITE_BOOST   # and the near-neutral light colours (whites)
    idx, w = tetra(pos)
    x = fit(idx, w, sw, delta, lam)
    lut = np.round(x * 16).astype(np.int16)
    info = dict(film=film, nodes=len(res), producible=int(ok.sum()), worst_residual_all=float(res.max()), worst_residual_producible=float(res[ok].max()),
                p99_residual_producible=float(np.percentile(res[ok], 99)), samples=len(std), max_abs_delta_levels=float(np.abs(lut).max() / 16))
    return lut, info


def main():
    coef = load_coef()
    films = [a for a in sys.argv[1:] if not a.startswith('-')] or list(SLUG)
    for film in films:
        lut, info = make(film, coef)
        out = SCRATCH / f'lut-{SLUG[film]}-full.npy'
        np.save(out, lut)
        print(json.dumps(info), '->', out, flush=True)


if __name__ == '__main__':
    main()
