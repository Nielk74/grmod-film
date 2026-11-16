import sys, numpy as np
from common import *
from engine import *
import films
from sheets import path_of
def run(key, scenes, lut=None):
    film, tf, ne = films.FILMS[key]; lut = lut if lut is not None else build_lut(tf, ne)
    for n in scenes:
        std = load_rgb8(path_of(n), 600); std = std[:, :std.shape[1] // 2 * 2]
        cam = camera_today(std, film)
        a, b = process_full(cam, lut); c0 = from_422(*a); c1 = from_422(*b)
        l0 = srgb_to_oklab(c0 / 255.); l1 = srgb_to_oklab(c1 / 255.)
        C0 = np.hypot(l0[..., 1], l0[..., 2]); h0 = np.arctan2(l0[..., 2], l0[..., 1])
        s = skin_weight(l0[..., 0], C0, h0); m = s > 0.5
        if m.sum() < 50: print(n, 'no skin px', m.sum()); continue
        C1 = np.hypot(l1[..., 1], l1[..., 2]); h1 = np.arctan2(l1[..., 2], l1[..., 1])
        d = lambda x: (np.degrees(x) + 360) % 360
        print(f"{key} {n}: skin px {m.mean()*100:.1f}%  cam C {C0[m].mean():.3f} h {d(h0[m]).mean():.0f}  eng C {C1[m].mean():.3f} h {d(h1[m]).mean():.0f}  ratio C {np.median(C1[m]/C0[m]):.2f}  dL {np.mean(l1[...,0][m]-l0[...,0][m]):+.3f}")
if __name__ == '__main__':
    run(sys.argv[1], sys.argv[2:])
