"""Shared helpers for the colour-engine prototype: Standard check, camera-today model, OkLab."""
import struct, json
import numpy as np
from PIL import Image, ImageOps

ROOT = r"C:\Users\Antoine\project\grmod-film"
OUT = ROOT + r"\scratch\colour-engine"
DIRS = [r"C:\Users\Antoine\Pictures\Ricoh", r"C:\Users\Antoine\Pictures\Ricoh2"]


def image_tone(path):
    """Ricoh maker note ('RICOH\0' + byte order + IFD), tag 0x004F ImageTone; 0x100 = Standard."""
    note = Image.open(path).getexif().get_ifd(0x8769).get(0x927C)
    if not note or not note.startswith(b"RICOH"):
        return None
    end = "<" if note[6:8] == b"II" else ">"
    n = struct.unpack(end + "H", note[8:10])[0]
    for i in range(n):
        tag, kind, _, value = struct.unpack(end + "HHI4s", note[10 + 12 * i: 22 + 12 * i])
        if tag == 0x004F:
            return struct.unpack(end + ("H" if kind == 3 else "I"), value[:2] if kind == 3 else value)[0]
    return None


def load_rgb8(path, width=None):
    im = ImageOps.exif_transpose(Image.open(path).convert("RGB"))
    if width and im.width > width:
        im = im.resize((width, round(im.height * width / im.width)), Image.LANCZOS)
    return np.asarray(im)


# ---- camera today: matrix, curves, post matrix as fitted (model of nativeGrid in film_pipeline_v2.ts)
_coef = None
def coef():
    global _coef
    if _coef is None:
        _coef = json.load(open(OUT + r"\coef.json", encoding="utf8"))
    return _coef


def camera_today(rgb8, film):
    c = coef()
    Sinv = np.array(c["Sinv"], np.float32)
    S = np.array(c["S"], np.float32)
    std = np.array(c["standardQ13"], np.float64).reshape(3, 3) / 8192
    f = c[film]
    M = (np.array(f["matrixQ13"], np.float64).reshape(3, 3) / 8192) @ np.linalg.inv(std)
    curves = [np.array(k, np.float32) for k in f["curves"]]
    post = np.array(f["postQ9"], np.float64).reshape(3, 3) / 512 if f["postQ9"] else np.eye(3)
    lin = Sinv[rgb8]
    out = np.empty(rgb8.shape, np.float32)
    cv = []
    for ch in range(3):
        l = np.clip(lin[..., 0] * M[ch, 0] + lin[..., 1] * M[ch, 1] + lin[..., 2] * M[ch, 2], 0, 1)
        d = np.interp(l * 4096, np.arange(4097), S)
        pos = np.clip(d * 16383 / 64, 0, 255)
        cv.append(np.interp(pos, np.arange(256), curves[ch]) / 16383)
    for ch in range(3):
        out[..., ch] = np.clip(post[ch, 0] * cv[0] + post[ch, 1] * cv[1] + post[ch, 2] * cv[2], 0, 1)
    return np.round(out * 255).astype(np.uint8)


# ---- OkLab (input/output: sRGB-encoded 0..1)
def s2l(c):
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)

def l2s(c):
    c = np.clip(c, 0, None)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * c ** (1 / 2.4) - 0.055)

_M1 = np.array([[0.4122214708, 0.5363325363, 0.0514459929], [0.2119034982, 0.6806995451, 0.1073969566], [0.0883024619, 0.2817188376, 0.6299787005]])
_M2 = np.array([[0.2104542553, 0.7936177850, -0.0040720468], [1.9779984951, -2.4285922050, 0.4505937099], [0.0259040371, 0.7827717662, -0.8086757660]])
_M1i, _M2i = np.linalg.inv(_M1), np.linalg.inv(_M2)

def srgb_to_oklab(rgb):
    lms = np.cbrt(s2l(rgb) @ _M1.T)
    return lms @ _M2.T

def oklab_to_lin(lab):
    lms = (lab @ _M2i.T) ** 3
    return lms @ _M1i.T

def oklab_to_srgb(lab):
    return l2s(np.clip(oklab_to_lin(lab), 0, 1))

def gamut_map(L, C, h):
    """OkLCh -> sRGB, reducing chroma (hue and lightness kept) until the colour is inside sRGB."""
    L = np.clip(L, 0, 1)
    def lin(Cc):
        return oklab_to_lin(np.stack([L, Cc * np.cos(h), Cc * np.sin(h)], -1))
    lo = np.zeros_like(C); hi = C.copy()
    ok = ((lin(hi) >= -0.0005) & (lin(hi) <= 1.0005)).all(-1)
    for _ in range(14):
        mid = (lo + hi) / 2
        m = ((lin(mid) >= -0.0005) & (lin(mid) <= 1.0005)).all(-1)
        lo = np.where(~ok & m, mid, lo); hi = np.where(~ok & ~m, mid, hi)
    Cf = np.where(ok, C, lo)
    return l2s(np.clip(lin(Cf), 0, 1))
