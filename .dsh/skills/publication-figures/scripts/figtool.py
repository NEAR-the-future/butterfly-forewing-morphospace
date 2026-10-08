#!/usr/bin/env python3
"""Deterministic raster figure tool for scientific artwork.

Edits are declared as an ordered JSON op list, so the same input plus the same
ops file always produces the same output. A run manifest records every op.

Usage:
  figtool.py probe   IMAGE [--json]
  figtool.py ops
  figtool.py apply   IMAGE --ops EDITS.json --out DIR [--manifest FILE] [--dry-run]
  figtool.py compose A B [C ...] --cols N --gutter PX [--labels a,b] --out FIG.tif
                     [--dpi N] [--label-size PT] [--background WHITE]
  figtool.py mm2px   --mm 89 --dpi 300
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    import numpy as np
    from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps
except Exception as exc:  # pragma: no cover
    raise SystemExit(f"Pillow and numpy are required: {exc}")

SAVE_EXT = {".tif": "TIFF", ".tiff": "TIFF", ".png": "PNG", ".jpg": "JPEG",
            ".jpeg": "JPEG", ".pdf": "PDF", ".bmp": "BMP", ".webp": "WEBP"}

FONT_CANDIDATES = [
    r"C:\Windows\Fonts\arial.ttf",
    r"C:\Windows\Fonts\Arial.ttf",
    r"C:\Windows\Fonts\Helvetica.ttf",
    r"C:\Windows\Fonts\segoeui.ttf",
    r"C:\Windows\Fonts\DejaVuSans.ttf",
]


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for cand in FONT_CANDIDATES:
        if Path(cand).is_file():
            try:
                return ImageFont.truetype(cand, size)
            except Exception:
                continue
    return ImageFont.load_default()


def mm_to_px(mm: float, dpi: float) -> int:
    return int(round(mm / 25.4 * dpi))


def px_to_mm(px: int, dpi: float) -> float:
    return round(px / dpi * 25.4, 2)


def as_uint8(arr: np.ndarray) -> np.ndarray:
    if arr.dtype == np.uint8:
        return arr
    if arr.dtype == np.uint16:
        return (arr / 257.0).round().astype(np.uint8)
    if np.issubdtype(arr.dtype, np.floating):
        mx = float(np.nanmax(arr)) if arr.size else 1.0
        scale = 255.0 if mx <= 1.0 else (255.0 / mx if mx > 255 else 1.0)
        return np.clip(arr * scale, 0, 255).astype(np.uint8)
    return np.clip(arr, 0, 255).astype(np.uint8)


def as_rgb(img: Image.Image) -> Image.Image:
    if img.mode in {"RGBA", "LA", "P"}:
        background = Image.new("RGBA", img.size, (255, 255, 255, 255))
        background.alpha_composite(img.convert("RGBA"))
        return background.convert("RGB")
    if img.mode == "L":
        return img.convert("RGB")
    if img.mode == "CMYK":
        return img.convert("RGB")
    return img.convert("RGB")


# ---------------------------------------------------------------------------
# ops
# ---------------------------------------------------------------------------

def op_crop(img, box, **kw):
    if not (isinstance(box, (list, tuple)) and len(box) == 4):
        raise ValueError("crop.box must be [x0, y0, x1, y1]")
    x0, y0, x1, y1 = (int(v) for v in box)
    w, h = img.size
    x0, y0 = max(0, min(x0, w - 1)), max(0, min(y0, h - 1))
    x1, y1 = max(x0 + 1, min(x1, w)), max(y0 + 1, min(y1, h))
    if (x0, y0, x1, y1) != tuple(int(v) for v in box):
        print(f"  note: crop box clamped to {(x0, y0, x1, y1)} for a {w}x{h} image", file=sys.stderr)
    return img.crop((x0, y0, x1, y1)), {"box": [x0, y0, x1, y1]}


def op_rotate(img, degrees=0, expand=True, background="white", **kw):
    return img.rotate(float(degrees), expand=bool(expand), resample=Image.BICUBIC,
                      fillcolor=background), {"degrees": degrees}


def op_flip(img, mode="horizontal", **kw):
    if mode in {"horizontal", "h", "x"}:
        return ImageOps.mirror(img), {"mode": "horizontal"}
    return ImageOps.flip(img), {"mode": "vertical"}


def op_resize(img, width=None, height=None, scale=None, resample="lanczos", **kw):
    w, h = img.size
    if scale:
        tw, th = max(1, int(round(w * float(scale)))), max(1, int(round(h * float(scale))))
    elif width and not height:
        tw, th = int(width), max(1, int(round(h * int(width) / w)))
    elif height and not width:
        th, tw = int(height), max(1, int(round(w * int(height) / h)))
    elif width and height:
        tw, th = int(width), int(height)
    else:
        raise ValueError("resize needs width, height, or scale")
    filt = {"nearest": Image.NEAREST, "bilinear": Image.BILINEAR,
            "bicubic": Image.BICUBIC, "lanczos": Image.LANCZOS}.get(str(resample).lower(),
                                                                    Image.LANCZOS)
    upscale = tw * th > w * h
    note = None
    if upscale:
        note = ("UPSCALING: output has more pixels than the source; this does NOT create "
                "resolution. Journals may reject upscaled artwork as low quality.")
        print(f"  WARNING: {note}", file=sys.stderr)
    return img.resize((tw, th), filt), {"size": [tw, th], "resample": resample,
                                        "upscaled": upscale, "warning": note}


def op_auto_levels(img, clip_percent=0.5, per_channel=False, **kw):
    rgb = as_rgb(img)
    arr = np.asarray(rgb).astype(np.float32)
    clip = max(0.0, float(clip_percent))
    if per_channel:
        out = np.empty_like(arr)
        for c in range(3):
            lo, hi = np.percentile(arr[:, :, c], [clip, 100 - clip])
            out[:, :, c] = _stretch(arr[:, :, c], lo, hi)
    else:
        lo, hi = np.percentile(arr, [clip, 100 - clip])
        out = _stretch(arr, lo, hi)
    return Image.fromarray(out.astype(np.uint8), "RGB"), {"clip_percent": clip_percent,
                                                          "per_channel": bool(per_channel)}


def _stretch(arr: np.ndarray, lo: float, hi: float) -> np.ndarray:
    if hi <= lo:
        return arr
    return np.clip((arr - lo) * (255.0 / (hi - lo)), 0, 255)


def op_levels(img, black=0, white=255, gamma=1.0, **kw):
    rgb = as_rgb(img)
    arr = np.asarray(rgb).astype(np.float32) / 255.0
    black, white = float(black) / 255.0, float(white) / 255.0
    if white <= black:
        raise ValueError("levels.white must exceed levels.black")
    arr = np.clip((arr - black) / (white - black), 0, 1)
    if float(gamma) != 1.0:
        arr = np.power(arr, 1.0 / float(gamma))
    return Image.fromarray((arr * 255).round().astype(np.uint8), "RGB"), {
        "black": black, "white": white, "gamma": gamma,
        "note": "non-linear operation: declare it in the figure legend" if float(gamma) != 1.0 else None}


def op_background_flatten(img, sigma=40, dark=True, **kw):
    """Divide out a low-frequency illumination field (flat-field correction)."""
    rgb = as_rgb(img)
    arr = np.asarray(rgb).astype(np.float32)
    gray = arr.mean(axis=2)
    background = np.asarray(
        Image.fromarray(as_uint8(gray), "L").filter(ImageFilter.GaussianBlur(float(sigma)))
    ).astype(np.float32)
    background = np.maximum(background, 1.0)
    target = float(np.percentile(background, 95)) if dark else float(np.percentile(background, 5))
    out = arr * (target / background[:, :, None])
    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8), "RGB"), {
        "sigma": sigma, "target": round(target, 1),
        "note": "non-linear local correction: declare it in the figure legend"}


def op_white_balance(img, mode="gray_world", **kw):
    rgb = as_rgb(img)
    arr = np.asarray(rgb).astype(np.float32)
    means = arr.reshape(-1, 3).mean(axis=0)
    if mode == "max":
        target = means.max()
    else:
        target = means.mean()
    gains = target / np.maximum(means, 1e-6)
    out = arr * gains[None, None, :]
    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8), "RGB"), {
        "gains": [round(float(g), 4) for g in gains], "mode": mode}


def op_desaturate(img, amount=1.0, **kw):
    rgb = as_rgb(img)
    gray = ImageOps.grayscale(rgb).convert("RGB")
    return Image.blend(rgb, gray, float(amount)), {"amount": amount}


def op_sharpen(img, percent=60, radius=1.2, threshold=3, **kw):
    return as_rgb(img).filter(ImageFilter.UnsharpMask(radius=float(radius),
                                                      percent=int(percent),
                                                      threshold=int(threshold))), {
        "percent": percent, "radius": radius, "threshold": threshold,
        "note": "sharpening is a non-linear operation: do not apply to quantitative images"}


def op_blur(img, radius=2.0, **kw):
    return as_rgb(img).filter(ImageFilter.GaussianBlur(float(radius))), {"radius": radius}


def op_denoise(img, radius=2, strength=0.6, **kw):
    rgb = as_rgb(img)
    smoothed = rgb.filter(ImageFilter.MedianFilter(size=int(radius) * 2 + 1))
    return Image.blend(rgb, smoothed, float(strength)), {"radius": radius, "strength": strength}


def op_flatten_background_to_white(img, threshold=240, **kw):
    rgb = as_rgb(img)
    arr = np.asarray(rgb).astype(np.float32)
    mask = arr.min(axis=2) >= float(threshold)
    arr[mask] = 255.0
    return Image.fromarray(arr.astype(np.uint8), "RGB"), {"threshold": threshold}


def op_to_grayscale(img, **kw):
    return ImageOps.grayscale(as_rgb(img)).convert("RGB"), {}


def op_to_rgb(img, **kw):
    return as_rgb(img), {}


def op_to_cmyk(img, **kw):
    return as_rgb(img).convert("CMYK"), {"note": "provide the journal's CMYK profile when available"}


def _scale_geom(img, geom: dict, from_size, op_name):
    """Scale annotation geometry recorded in pre-resize pixels."""
    sx = img.size[0] / max(1, from_size[0])
    sy = img.size[1] / max(1, from_size[1])
    out = dict(geom)
    for key in ("xy", "start", "end", "box"):
        if key in out and isinstance(out[key], (list, tuple)):
            pts = list(out[key])
            out[key] = [pts[0] * sx, pts[1] * sy] if len(pts) == 2 else \
                [pts[0] * sx, pts[1] * sy, pts[2] * sx, pts[3] * sy]
    for key in ("length_px", "thickness", "margin", "size", "width"):
        if key in out and isinstance(out[key], (int, float)):
            out[key] = out[key] * (sx + sy) / 2.0
    for key in ("size", "thickness", "length_px", "margin", "width"):
        if key in out and isinstance(out[key], float):
            out[key] = int(round(out[key]))
    return out


ANCHORS = {"nw": (0.0, 0.0), "n": (0.5, 0.0), "ne": (1.0, 0.0),
           "w": (0.0, 0.5), "center": (0.5, 0.5), "e": (1.0, 0.5),
           "sw": (0.0, 1.0), "s": (0.5, 1.0), "se": (1.0, 1.0)}


def op_label_panel(img, text="a", anchor="nw", size=64, color="black", margin=24, **kw):
    out = as_rgb(img).copy()
    draw = ImageDraw.Draw(out)
    font = load_font(int(size))
    ax, ay = ANCHORS.get(str(anchor).lower(), ANCHORS["nw"])
    w, h = out.size
    bbox = draw.textbbox((0, 0), str(text), font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    x = ax * (w - tw - 2 * margin) + margin - bbox[0]
    y = ay * (h - th - 2 * margin) + margin - bbox[1]
    draw.text((x, y), str(text), fill=color, font=font)
    return out, {"text": text, "anchor": anchor, "size": size,
                 "position": [round(x), round(y)]}


def op_draw_scalebar(img, length_px, thickness=8, color="white", anchor="se", margin=24,
                     label=None, label_size=None, label_color=None, outline=True, **kw):
    out = as_rgb(img).copy()
    draw = ImageDraw.Draw(out)
    w, h = out.size
    length = int(length_px)
    thick = max(1, int(thickness))
    ax, ay = ANCHORS.get(str(anchor).lower(), ANCHORS["se"])
    x0 = int(ax * (w - length - 2 * margin) + margin)
    y0 = int(ay * (h - thick - 2 * margin) + margin)
    if outline:
        draw.rectangle([x0 - 2, y0 - 2, x0 + length + 2, y0 + thick + 2],
                       fill="black" if str(color).lower() != "black" else "white")
    draw.rectangle([x0, y0, x0 + length, y0 + thick], fill=color)
    label_pos = None
    if label:
        font = load_font(int(label_size or max(16, thick * 3)))
        bbox = draw.textbbox((0, 0), str(label), font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        lx = x0 + (length - tw) // 2 - bbox[0]
        ly = y0 - th - 8 - bbox[1] if ay > 0.5 else y0 + thick + 8 - bbox[1]
        ly = max(0, min(ly, h - th - 1))
        draw.text((lx, ly), str(label), fill=label_color or color, font=font)
        label_pos = [int(lx), int(ly)]
    return out, {"length_px": length, "thickness": thick, "anchor": anchor,
                 "label": label, "label_position": label_pos,
                 "warning": "verify the scale-bar length after every resize"}


def op_add_arrow(img, start, end, color="white", width=6, head=18, outline=True, **kw):
    out = as_rgb(img).copy()
    draw = ImageDraw.Draw(out)
    import math
    (x0, y0), (x1, y1) = (float(start[0]), float(start[1])), (float(end[0]), float(end[1]))
    draw.line([(x0, y0), (x1, y1)], fill=color, width=int(width))
    ang = math.atan2(y1 - y0, x1 - x0)
    for sign in (1, -1):
        a = ang + sign * math.radians(150)
        draw.line([(x1, y1), (x1 + float(head) * math.cos(a), y1 + float(head) * math.sin(a))],
                  fill=color, width=int(width))
    return out, {"start": [x0, y0], "end": [x1, y1], "width": width, "head": head}


def op_draw_rectangle(img, box, color="red", width=4, **kw):
    out = as_rgb(img).copy()
    draw = ImageDraw.Draw(out)
    draw.rectangle([float(v) for v in box], outline=color, width=int(width))
    return out, {"box": list(box), "color": color, "width": width}


def op_colorize_map(img, cmap="viridis", **kw):
    """Map a single-channel image through a perceptually uniform colour map."""
    rgb = as_rgb(img)
    arr = np.asarray(ImageOps.grayscale(rgb)).astype(np.float32) / 255.0
    stops = {
        "viridis": [(68, 1, 84), (59, 82, 139), (33, 145, 140), (94, 201, 98), (253, 231, 37)],
        "magma": [(0, 0, 4), (81, 18, 124), (183, 55, 121), (252, 137, 97), (252, 253, 191)],
        "cividis": [(0, 32, 76), (39, 79, 122), (89, 124, 130), (144, 171, 133), (253, 234, 69)],
        "gray": [(0, 0, 0), (255, 255, 255)],
        "blue_white_red": [(33, 102, 172), (255, 255, 255), (178, 24, 43)],
    }
    if cmap not in stops:
        raise ValueError(f"unknown cmap '{cmap}'; available: {sorted(stops)}")
    cs = np.array(stops[cmap], dtype=np.float32)
    pos = np.linspace(0.0, 1.0, len(cs))
    out = np.stack([np.interp(arr, pos, cs[:, c]) for c in range(3)], axis=2)
    return Image.fromarray(out.astype(np.uint8), "RGB"), {"cmap": cmap}


OPS = {
    "crop": op_crop, "rotate": op_rotate, "flip": op_flip, "resize": op_resize,
    "auto_levels": op_auto_levels, "levels": op_levels,
    "background_flatten": op_background_flatten, "white_balance": op_white_balance,
    "desaturate": op_desaturate, "sharpen": op_sharpen, "blur": op_blur, "denoise": op_denoise,
    "flatten_background_to_white": op_flatten_background_to_white,
    "to_grayscale": op_to_grayscale, "to_rgb": op_to_rgb, "to_cmyk": op_to_cmyk,
    "colorize_map": op_colorize_map, "label_panel": op_label_panel,
    "draw_scalebar": op_draw_scalebar, "annotate_scalebar": op_draw_scalebar,
    "add_arrow": op_add_arrow, "draw_rectangle": op_draw_rectangle,
}


def apply_ops(img: Image.Image, ops: list[dict], manifest: list[dict]) -> Image.Image:
    """Apply ops in order; the annotation compositing loop runs after all
    geometry/colour ops so annotation geometry is authored in final pixels."""
    annotations = []
    for entry in ops:
        if not isinstance(entry, dict) or "op" not in entry:
            raise ValueError(f"each op must be an object with an 'op' key: {entry!r}")
        name = str(entry["op"]).lower()
        params = {k: v for k, v in entry.items() if k != "op"}
        if name == "compose":
            raise ValueError("'compose' is a top-level command, not a step; use figtool compose")
        if name == "save":
            continue
        if name in {"label_panel", "draw_scalebar", "annotate_scalebar", "add_arrow",
                    "draw_rectangle"}:
            annotations.append((name, params))
            continue
        if name not in OPS:
            raise ValueError(f"unknown op '{name}'. Run `figtool.py ops` for the list.")
        before = img.size
        img, info = OPS[name](img, **params)
        manifest.append({"op": name, "params": params, "result": info,
                         "size_before": list(before), "size_after": list(img.size),
                         "mode": img.mode})
    for name, params in annotations:
        before = img.size
        img, info = OPS[name](img, **params)
        manifest.append({"op": name, "params": params, "result": info,
                         "size_before": list(before), "size_after": list(img.size),
                         "mode": img.mode,
                         "stage": "annotation (applied after geometry and colour ops)"})
    return img


def save_image(img: Image.Image, path: Path, dpi: int, compression: str | None) -> dict:
    fmt = SAVE_EXT.get(path.suffix.lower())
    if fmt is None:
        raise ValueError(f"unsupported output extension '{path.suffix}'; "
                         f"use one of {sorted(SAVE_EXT)}")
    path.parent.mkdir(parents=True, exist_ok=True)
    kwargs: dict = {}
    if fmt == "TIFF":
        kwargs["compression"] = {"tiff_lzw": "tiff_lzw", "lzw": "tiff_lzw",
                                 "deflate": "tiff_deflate", "none": None,
                                 "jpeg": "jpeg"}.get(str(compression or "tiff_lzw").lower(),
                                                     "tiff_lzw")
        kwargs["dpi"] = (dpi, dpi)
    elif fmt == "PNG":
        kwargs["dpi"] = (dpi, dpi)
        kwargs["optimize"] = True
    elif fmt == "JPEG":
        kwargs["quality"] = 95
        kwargs["dpi"] = (dpi, dpi)
        kwargs["subsampling"] = 0
    elif fmt == "PDF":
        kwargs["resolution"] = float(dpi)
    img.save(str(path), format=fmt, **kwargs)
    return {"path": str(path), "format": fmt, "mode": img.mode, "size": list(img.size),
            "dpi": dpi, "bytes": path.stat().st_size,
            "width_mm_at_dpi": px_to_mm(img.size[0], dpi),
            "height_mm_at_dpi": px_to_mm(img.size[1], dpi)}


# ---------------------------------------------------------------------------
# commands
# ---------------------------------------------------------------------------

def cmd_probe(args) -> int:
    path = Path(args.image)
    with Image.open(path) as im:
        dpi = im.info.get("dpi")
        info = {
            "path": str(path),
            "format": im.format,
            "size": list(im.size),
            "mode": im.mode,
            "bit_depth_per_channel": 16 if im.mode.startswith("I;16") else (
                8 if im.mode in {"L", "RGB", "RGBA", "P", "CMYK", "1"} else None),
            "has_alpha": im.mode in {"RGBA", "LA", "PA"},
            "dpi": list(dpi) if isinstance(dpi, tuple) else dpi,
            "icc_profile_bytes": len(im.info.get("icc_profile", b"") or b""),
            "is_animated": getattr(im, "n_frames", 1) > 1,
            "bytes": path.stat().st_size,
        }
        if isinstance(dpi, tuple) and dpi[0]:
            info["width_mm_at_stated_dpi"] = px_to_mm(im.size[0], dpi[0])
            info["height_mm_at_stated_dpi"] = px_to_mm(im.size[1], dpi[1])
        arr = np.asarray(im.convert("RGB"))
        gray = arr.mean(axis=2)
        info["luminance"] = {
            "min": int(gray.min()), "max": int(gray.max()),
            "mean": round(float(gray.mean()), 1),
            "p1": round(float(np.percentile(gray, 1)), 1),
            "p50": round(float(np.percentile(gray, 50)), 1),
            "p99": round(float(np.percentile(gray, 99)), 1),
            "clipped_black_pct": round(float((gray <= 1).mean() * 100), 3),
            "clipped_white_pct": round(float((gray >= 254).mean() * 100), 3),
        }
        info["high_frequency_energy"] = round(
            float(np.abs(np.diff(gray, axis=1)).mean()) if gray.shape[1] > 1 else 0.0, 3)
        info["notes"] = []
        if info["luminance"]["clipped_white_pct"] > 5:
            info["notes"].append("more than 5% of pixels are clipped white — check exposure")
        if info["luminance"]["clipped_black_pct"] > 5:
            info["notes"].append("more than 5% of pixels are clipped black — check exposure")
        if not dpi:
            info["notes"].append("no DPI recorded; set it explicitly on export")
    if args.json:
        print(json.dumps(info, indent=2, ensure_ascii=False))
    else:
        for k, v in info.items():
            print(f"{k}: {v}")
    return 0


def cmd_ops(args) -> int:
    print("Available ops (parameters are the op's JSON keys):\n")
    docs = {
        "crop": "box:[x0,y0,x1,y1]",
        "rotate": "degrees, expand, background",
        "flip": "mode: horizontal|vertical",
        "resize": "width|height|scale, resample: nearest|bilinear|bicubic|lanczos",
        "auto_levels": "clip_percent, per_channel",
        "levels": "black(0-255), white(0-255), gamma",
        "background_flatten": "sigma, dark  [flat-field / uneven-illumination correction]",
        "white_balance": "mode: gray_world|max",
        "desaturate": "amount(0-1)",
        "sharpen": "percent, radius, threshold",
        "blur": "radius",
        "denoise": "radius, strength",
        "flatten_background_to_white": "threshold",
        "to_grayscale": "-", "to_rgb": "-", "to_cmyk": "-",
        "colorize_map": "cmap: viridis|magma|cividis|gray|blue_white_red",
        "label_panel": "text, anchor(nw|n|ne|w|center|e|sw|s|se), size, color, margin",
        "annotate_scalebar": "length_px, thickness, label, label_size, color, anchor, margin",
        "add_arrow": "start:[x,y], end:[x,y], color, width, head",
        "draw_rectangle": "box:[x0,y0,x1,y1], color, width",
        "save": "path, dpi, compression (tiff_lzw|tiff_deflate|none|jpeg)",
    }
    for name, doc in docs.items():
        print(f"  {name:26} {doc}")
    return 0


def cmd_apply(args) -> int:
    src = Path(args.image)
    ops_path = Path(args.ops)
    ops = json.loads(ops_path.read_text(encoding="utf-8-sig"))
    if isinstance(ops, dict):
        ops = ops.get("ops", [])
    if not isinstance(ops, list):
        raise SystemExit("the ops file must contain a JSON list of op objects")
    save_entries = [o for o in ops if isinstance(o, dict) and str(o.get("op", "")).lower() == "save"]
    out_dir = Path(args.out) if args.out else src.parent
    target = Path(save_entries[-1]["path"]) if save_entries and save_entries[-1].get("path") else None
    if target is None:
        target = out_dir / f"{src.stem}_edited{src.suffix or '.tif'}"
    elif not target.is_absolute() and args.out:
        target = out_dir / target.name
    dpi = int((save_entries[-1].get("dpi") if save_entries else None) or args.dpi)
    compression = (save_entries[-1].get("compression") if save_entries else None) or args.compression

    with Image.open(src) as im:
        manifest: list[dict] = [{"op": "open", "params": {"path": str(src)},
                                 "result": {"size": list(im.size), "mode": im.mode,
                                            "format": im.format}}]
        img = im.copy()
    if args.dry_run:
        print(json.dumps({"plan": ops, "target": str(target), "dpi": dpi},
                         indent=2, ensure_ascii=False))
        return 0

    img = apply_ops(img, ops, manifest)
    result = save_image(img, target, dpi, compression)
    manifest.append({"op": "save", "params": {"path": str(target), "dpi": dpi,
                                              "compression": compression}, "result": result})
    manifest_path = Path(args.manifest) if args.manifest else out_dir / f"{target.stem}.manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps({
        "source": str(src.resolve()),
        "ops_file": str(ops_path.resolve()),
        "output": result,
        "steps": manifest,
        "integrity_note": ("Non-linear steps are flagged in the manifest. Declare them in the "
                           "figure legend. Verify that no operation misrepresents the data."),
    }, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {target} ({result['size'][0]}x{result['size'][1]} px, {result['mode']}, "
          f"{px_to_mm(result['size'][0], dpi)}x{px_to_mm(result['size'][1], dpi)} mm at {dpi} dpi)")
    print(f"manifest: {manifest_path}")
    return 0


def cmd_compose(args) -> int:
    panels = [Path(p) for p in args.panels]
    cols = max(1, int(args.cols))
    gutter = int(args.gutter)
    dpi = int(args.dpi)
    labels = [s.strip() for s in (args.labels or "").split(",") if s.strip()]
    imgs = []
    for p in panels:
        with Image.open(p) as im:
            imgs.append(as_rgb(im).copy())

    # optional: scale the whole grid so the figure lands on a journal column width
    uniform = 1.0
    if args.width_mm:
        cell_w = max(im.size[0] for im in imgs)
        natural = cols * cell_w + (cols - 1) * gutter
        target_px = mm_to_px(float(args.width_mm), dpi)
        uniform = target_px / max(1, natural)
        if abs(uniform - 1.0) > 1e-3:
            imgs = [im.resize((max(1, int(round(im.size[0] * uniform))),
                               max(1, int(round(im.size[1] * uniform)))), Image.LANCZOS)
                    for im in imgs]
            gutter = max(1, int(round(gutter * uniform)))

    rows = (len(imgs) + cols - 1) // cols
    cell_w = max(im.size[0] for im in imgs)
    cell_h = max(im.size[1] for im in imgs)
    width = cols * cell_w + (cols - 1) * gutter
    height = rows * cell_h + (rows - 1) * gutter
    canvas = Image.new("RGB", (width, height), args.background)
    placed = []
    for idx, im in enumerate(imgs):
        r, c = divmod(idx, cols)
        x = c * (cell_w + gutter) + (cell_w - im.size[0]) // 2
        y = r * (cell_h + gutter) + (cell_h - im.size[1]) // 2
        canvas.paste(im, (x, y))
        placed.append({"panel": str(panels[idx]), "position": [x, y], "size": list(im.size)})
    if labels:
        for idx, text in enumerate(labels[:len(imgs)]):
            r, c = divmod(idx, cols)
            x = c * (cell_w + gutter)
            y = r * (cell_h + gutter)
            font = load_font(max(10, int(round(int(args.label_size) * uniform))))
            draw = ImageDraw.Draw(canvas)
            draw.text((x + max(4, int(8 * uniform)), y + max(3, int(6 * uniform))),
                      text, fill=args.label_color, font=font)
    out = Path(args.out)
    result = save_image(canvas, out, dpi, args.compression)
    manifest_path = out.with_suffix(out.suffix + ".manifest.json")
    manifest_path.write_text(json.dumps({
        "compose": {"cols": cols, "gutter": gutter, "panels": placed, "labels": labels,
                    "uniform_scale": round(uniform, 4),
                    "requested_width_mm": args.width_mm,
                    "achieved_width_mm": result["width_mm_at_dpi"]},
        "output": result,
        "warning": ("panels were uniformly scaled to hit the requested width; verify every scale "
                    "bar length and font size in the result"
                    if abs(uniform - 1.0) > 1e-3 else None),
    }, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {out} ({result['size'][0]}x{result['size'][1]} px, "
          f"{result['width_mm_at_dpi']}x{result['height_mm_at_dpi']} mm at {dpi} dpi)")
    if abs(uniform - 1.0) > 1e-3:
        print(f"uniform scale applied: {uniform:.4f} — re-verify scale bars and text sizes")
    return 0


def cmd_mm2px(args) -> int:
    px = mm_to_px(float(args.mm), float(args.dpi))
    print(json.dumps({"mm": args.mm, "dpi": args.dpi, "px": px,
                      "single_column_85mm": mm_to_px(85, float(args.dpi)),
                      "one_and_half_column_114mm": mm_to_px(114, float(args.dpi)),
                      "double_column_174mm": mm_to_px(174, float(args.dpi))}, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    ap = argparse.ArgumentParser(description="Deterministic raster figure tool.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_probe = sub.add_parser("probe", help="report image properties before editing")
    p_probe.add_argument("image")
    p_probe.add_argument("--json", action="store_true")
    p_probe.set_defaults(func=cmd_probe)

    p_ops = sub.add_parser("ops", help="list available operations")
    p_ops.set_defaults(func=cmd_ops)

    p_apply = sub.add_parser("apply", help="apply a JSON op list to one image")
    p_apply.add_argument("image")
    p_apply.add_argument("--ops", required=True)
    p_apply.add_argument("--out")
    p_apply.add_argument("--manifest")
    p_apply.add_argument("--dpi", type=int, default=300)
    p_apply.add_argument("--compression", default="tiff_lzw")
    p_apply.add_argument("--dry-run", action="store_true")
    p_apply.set_defaults(func=cmd_apply)

    p_comp = sub.add_parser("compose", help="assemble a multi-panel figure")
    p_comp.add_argument("panels", nargs="+")
    p_comp.add_argument("--cols", type=int, default=2)
    p_comp.add_argument("--gutter", type=int, default=24)
    p_comp.add_argument("--labels", default="")
    p_comp.add_argument("--label-size", type=int, default=64)
    p_comp.add_argument("--label-color", default="black")
    p_comp.add_argument("--background", default="white")
    p_comp.add_argument("--width-mm", type=float, default=None,
                        help="uniformly scale the whole grid to this printed width "
                             "(e.g. 89 single column, 183 double column)")
    p_comp.add_argument("--out", required=True)
    p_comp.add_argument("--dpi", type=int, default=300)
    p_comp.add_argument("--compression", default="tiff_lzw")
    p_comp.set_defaults(func=cmd_compose)

    p_mm = sub.add_parser("mm2px", help="convert millimetres to pixels at a DPI")
    p_mm.add_argument("--mm", type=float, required=True)
    p_mm.add_argument("--dpi", type=float, default=300)
    p_mm.set_defaults(func=cmd_mm2px)

    args = ap.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
