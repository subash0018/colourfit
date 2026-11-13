"""Photo processing for Colour-Fit.

process_photo() takes an uploaded clothing photo and returns:
  * a cut-out of the garment on a transparent background (PNG-ready),
  * the garment's dominant colour, matched to the nearest named colour.

Needs: Pillow and numpy.  Optional: scipy (faster) and rembg (better cut-outs
on busy backgrounds).  It never raises for a bad photo it can still read:
if the garment can't be separated it falls back to the whole photo and says so.
"""
from collections import deque

import numpy as np
from PIL import Image, ImageFilter, ImageOps

try:  # optional, only used to speed things up
    from scipy import ndimage as _ndi  # type: ignore  # pyright: ignore[reportMissingImports]
except Exception:  # pragma: no cover
    _ndi = None

MAX_SIDE = 520     # photos are shrunk to this before processing and saving
MIN_SIDE = 32      # anything smaller is rejected as unusable


class PhotoError(ValueError):
    """The file could not be read as a usable photo."""


# --------------------------------------------------------------------------
# Colour helpers
# --------------------------------------------------------------------------
def _hex_to_rgb(h):
    h = h.lstrip("#")
    return np.array([int(h[i:i + 2], 16) for i in (0, 2, 4)], dtype=float)


def _to_lab(rgb):
    """sRGB (0-255) -> CIE Lab. Works on arrays shaped (..., 3)."""
    c = np.asarray(rgb, dtype=float) / 255.0
    c = np.where(c > 0.04045, ((c + 0.055) / 1.055) ** 2.4, c / 12.92)
    m = np.array([[0.4124, 0.3576, 0.1805],
                  [0.2126, 0.7152, 0.0722],
                  [0.0193, 0.1192, 0.9505]])
    xyz = c @ m.T / np.array([0.95047, 1.0, 1.08883])
    f = np.where(xyz > 0.008856, np.cbrt(xyz), 7.787 * xyz + 16 / 116)
    return np.stack([116 * f[..., 1] - 16,
                     500 * (f[..., 0] - f[..., 1]),
                     200 * (f[..., 1] - f[..., 2])], axis=-1)


def _top_colour(pixels):
    """Mean colour of the most populated coarse colour bin."""
    q = pixels >> 5                                   # 8 levels per channel
    key = q[:, 0].astype(int) * 64 + q[:, 1].astype(int) * 8 + q[:, 2].astype(int)
    vals, counts = np.unique(key, return_counts=True)
    return pixels[key == vals[counts.argmax()]].mean(axis=0)


def _dominant_rgb(pixels):
    """Main colour of an (N, 3) uint8 array.

    If the garment is mostly white/grey/black but a clear colour covers a good
    share of it (a striped or printed shirt), that colour is reported instead.
    """
    if len(pixels) == 0:
        raise PhotoError("no pixels to read a colour from")
    if len(pixels) > 20000:
        idx = np.random.RandomState(0).choice(len(pixels), 20000, replace=False)
        pixels = pixels[idx]
    best = _top_colour(pixels)
    lab = _to_lab(best)
    if np.hypot(lab[1], lab[2]) < 12:                 # winner is neutral
        lab_all = _to_lab(pixels.astype(float))
        chromatic = np.hypot(lab_all[:, 1], lab_all[:, 2]) >= 20
        if chromatic.mean() >= 0.3:
            best = _top_colour(pixels[chromatic])
    return best


def name_colour(rgb, palette):
    """Nearest named colour. palette: {name: '#RRGGBB'}. Returns (name, hex, confidence)."""
    names = list(palette)
    pal_lab = _to_lab(np.array([_hex_to_rgb(palette[n]) for n in names]))
    lab = _to_lab(rgb)
    dist = np.linalg.norm(pal_lab - lab, axis=1)
    i = int(dist.argmin())
    conf = "high" if dist[i] < 14 else "medium" if dist[i] < 28 else "low"
    return names[i], palette[names[i]], conf


# --------------------------------------------------------------------------
# Segmentation helpers
# --------------------------------------------------------------------------
def _label(mask):
    """Connected components (4-neighbour). Returns (labels, count)."""
    if _ndi is not None:
        return _ndi.label(mask)
    h, w = mask.shape
    lab = np.zeros((h, w), dtype=np.int32)
    n = 0
    for y, x in zip(*np.nonzero(mask)):
        if lab[y, x]:
            continue
        n += 1
        lab[y, x] = n
        dq = deque([(y, x)])
        while dq:
            cy, cx = dq.popleft()
            for ny, nx in ((cy + 1, cx), (cy - 1, cx), (cy, cx + 1), (cy, cx - 1)):
                if 0 <= ny < h and 0 <= nx < w and mask[ny, nx] and not lab[ny, nx]:
                    lab[ny, nx] = n
                    dq.append((ny, nx))
    return lab, n


def _grow(mask, steps, shrink=False):
    """Dilate (or erode) a boolean mask by `steps` pixels."""
    img = Image.fromarray((mask * 255).astype("uint8"))
    f = ImageFilter.MinFilter(3) if shrink else ImageFilter.MaxFilter(3)
    for _ in range(max(steps, 0)):
        img = img.filter(f)
    return np.array(img) > 127


def _border_background(rgb, tol):
    """Background connected to the photo's edge.

    Returns (mask, bg_colour), or None when the edge isn't one plain colour.
    Thin background-coloured channels (e.g. white stripes that reach the
    garment's edge) are closed off first so the fill can't leak into the garment.
    """
    h, w, _ = rgb.shape
    t = max(2, int(min(h, w) * 0.02))
    border = np.concatenate([rgb[:t].reshape(-1, 3), rgb[-t:].reshape(-1, 3),
                             rgb[:, :t].reshape(-1, 3), rgb[:, -t:].reshape(-1, 3)]).astype(float)
    bg = np.median(border, axis=0)
    if (np.linalg.norm(border - bg, axis=1) < max(tol, 30)).mean() < 0.6:
        return None
    close = np.linalg.norm(rgb.astype(float) - bg, axis=2) < tol
    r = max(3, int(max(h, w) * 0.02))
    close = _grow(_grow(close, r, shrink=True), r)          # opening: drops narrow channels
    lab, _ = _label(close)
    edge_labels = np.unique(np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]]))
    edge_labels = edge_labels[edge_labels > 0]
    return np.isin(lab, edge_labels), bg


def _remove_shadow(rgb, fg, bgc):
    """Trim the soft shadow a garment casts on its backdrop.

    A shadow is a darker, same-hue version of the background that sits right
    next to it and is clearly not the garment's own colour.
    """
    if bgc.max() < 40:
        return fg
    h, w, _ = rgb.shape
    band = max(6, int(max(h, w) * 0.035))
    px = rgb.astype(float)
    c = px @ bgc / (bgc @ bgc)
    resid = np.linalg.norm(px - c[..., None] * bgc, axis=2)
    shade = (c > 0.5) & (c < 0.97) & (resid < 16)
    core = _grow(fg, band, shrink=True)
    if core.sum() < 50:
        return fg
    dom = _dominant_rgb(rgb[core])
    far = np.linalg.norm(_to_lab(px) - _to_lab(dom), axis=2) > 12
    near_bg = _grow(~fg, band)
    return fg & ~(near_bg & shade & far)


def _clean_mask(fg):
    """Keep the main object (plus any big pieces of it) and smooth the edge."""
    lab, n = _label(fg)
    if n == 0:
        return None
    sizes = np.bincount(lab.ravel())
    sizes[0] = 0
    keep = sizes >= max(sizes.max() * 0.1, 1)
    keep[0] = False
    fg = keep[lab]
    m = Image.fromarray((fg * 255).astype("uint8"))
    m = m.filter(ImageFilter.MinFilter(3)).filter(ImageFilter.MaxFilter(3))   # remove specks
    m = m.filter(ImageFilter.MaxFilter(3)).filter(ImageFilter.MinFilter(3))   # close pinholes
    return np.array(m) > 127


def _mask_is_plausible(fg):
    """A good garment mask is a solid blob that fills a fair part of the photo."""
    if fg is None or not fg.any():
        return False
    h, w = fg.shape
    ys, xs = np.nonzero(fg)
    bbox = (ys.max() - ys.min() + 1) * (xs.max() - xs.min() + 1)
    frac = fg.mean()
    return 0.04 <= frac <= 0.9 and bbox / (h * w) >= 0.1 and fg.sum() / bbox >= 0.35


def _segment(img_rgba):
    """Return a boolean foreground mask, or None if nothing reliable was found."""
    arr = np.array(img_rgba)
    rgb, alpha = arr[..., :3], arr[..., 3]

    # 1. Photo already has a transparent background.
    if (alpha < 250).mean() > 0.03 and (alpha > 200).mean() > 0.03:
        fg = _clean_mask(alpha > 24)
        if _mask_is_plausible(fg):
            return fg

    # 2. rembg, if the user installed it (best quality on busy backgrounds).
    try:
        from rembg import remove  # type: ignore  # pyright: ignore[reportMissingImports]
        out = np.array(remove(img_rgba.convert("RGB")).convert("RGBA"))
        fg = _clean_mask(out[..., 3] > 127)
        if _mask_is_plausible(fg):
            return fg
    except Exception:
        pass

    # 3. Plain-background photos: remove everything joined to the edge.
    for tol in (40, 26, 14):
        found = _border_background(rgb, tol)
        if found is None:
            break
        bg_mask, bgc = found
        fg = _clean_mask(~bg_mask)
        if fg is not None:
            fg = _clean_mask(_remove_shadow(rgb, fg, bgc))
        if _mask_is_plausible(fg):
            return fg
    return None


# --------------------------------------------------------------------------
# Public function
# --------------------------------------------------------------------------
def process_photo(file_like, palette):
    """Cut out the garment and detect its colour.

    Returns a dict:
      image       PIL RGBA image (cut-out when cutout is True)
      colour      nearest palette name, e.g. 'navy'
      hex         that colour's hex code
      confidence  'high' | 'medium' | 'low'
      cutout      True if the background was removed
      note        short message for the user
    Raises PhotoError only if the file is not a readable photo.
    """
    try:
        img = Image.open(file_like)
        img.load()
        img = ImageOps.exif_transpose(img).convert("RGBA")
    except Exception as exc:
        raise PhotoError("That file could not be read as a photo.") from exc

    w, h = img.size
    if min(w, h) < MIN_SIDE:
        raise PhotoError("That photo is too small. Use one at least 32 pixels wide.")
    scale = MAX_SIDE / max(w, h)
    if scale < 1:
        img = img.resize((max(1, round(w * scale)), max(1, round(h * scale))), Image.LANCZOS)

    arr = np.array(img)
    fg = None
    try:
        fg = _segment(img)
    except Exception:
        fg = None   # never let segmentation break an upload

    if fg is not None:
        # Colour from the garment's inside (edge pixels blend with the background).
        core = np.array(Image.fromarray((fg * 255).astype("uint8")).filter(ImageFilter.MinFilter(5))) > 127
        if core.sum() < 50:
            core = fg
        rgb_px = arr[..., :3][core]

        ys, xs = np.nonzero(fg)
        pad = int(max(arr.shape[:2]) * 0.02)
        y0, y1 = max(ys.min() - pad, 0), min(ys.max() + pad + 1, arr.shape[0])
        x0, x1 = max(xs.min() - pad, 0), min(xs.max() + pad + 1, arr.shape[1])

        soft = Image.fromarray((fg * 255).astype("uint8")).filter(ImageFilter.GaussianBlur(1.1))
        out = arr.copy()
        out[..., 3] = np.minimum(np.array(soft), out[..., 3])
        image = Image.fromarray(out[y0:y1, x0:x1], "RGBA")
        cutout, note = True, "Background removed."
    else:
        # Couldn't separate the garment: keep the whole photo, read colour from the middle.
        hh, ww = arr.shape[:2]
        centre = arr[int(hh * .3):int(hh * .7), int(ww * .3):int(ww * .7), :3].reshape(-1, 3)
        rgb_px = centre if len(centre) else arr[..., :3].reshape(-1, 3)
        image = img
        cutout = False
        note = "The clothing couldn't be separated from the background, so the whole photo is used."

    name, hexcode, conf = name_colour(_dominant_rgb(rgb_px), palette)
    return {"image": image, "colour": name, "hex": hexcode,
            "confidence": conf, "cutout": cutout, "note": note}