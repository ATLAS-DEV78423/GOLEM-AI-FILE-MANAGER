"""Icon system — built-in SVG paths rendered to ``tk.PhotoImage``.

We don't ship PNGs (extra build step, extra size in the installer,
extra platform-specific DPI variants). Instead, every icon is a tiny
SVG path string parsed by ``svg_to_photoimage``, which produces a
``tk.PhotoImage`` at the requested pixel size. The renderer is
~80 lines and handles the path subset we use: ``M`` (move), ``L`` (line),
``H`` (horizontal line), ``V`` (vertical line), ``Z`` (close),
``C`` (cubic bezier), and ``Q`` (quadratic bezier). That's enough for
crisp 1-color glyphs.

Add an icon by appending to ``ICON_LIBRARY`` — a name, an SVG path,
and a default viewBox (typically 24×24).
"""
from __future__ import annotations

import math
import re
import tkinter as tk
from dataclasses import dataclass

from .ui_theme import ICON_SIZE

# ---------------------------------------------------------------------------
# Icon definitions
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class IconDef:
    name: str
    svg: str                # 24x24 viewBox
    default_size: int = ICON_SIZE.DEFAULT


# Each icon is a single-path SVG silhouette in a 24×24 viewBox.
# `stroke` in the source is the renderer's fill color; we set fill when
# drawing.
ICON_LIBRARY: tuple[IconDef, ...] = (
    IconDef("search",
        "M11 4a7 7 0 1 1-4.95 11.95l-3.78 3.78a1 1 0 0 1-1.42-1.42l3.78-3.78A7 7 0 0 1 11 4zm0 2a5 5 0 1 0 0 10 5 5 0 0 0 0-10z"),
    IconDef("file",
        "M6 2a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8.41a2 2 0 0 0-.59-1.41l-4.41-4.41A2 2 0 0 0 13.59 2H6zm0 2h7v5h5v11H6V4zm9 1.41L17.59 8H15V5.41z"),
    IconDef("folder",
        "M3 6a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V6zm2 0v10h14V8h-7.41l-2-2H5z"),
    IconDef("check",
        "M9.55 17.6 4 12.05l1.4-1.4 4.15 4.15L18.6 5.75 20 7.15z"),
    IconDef("x",
        "M6.4 4.99 12 10.59l5.6-5.6 1.4 1.4-5.6 5.6 5.6 5.6-1.4 1.4-5.6-5.6-5.6 5.6-1.4-1.4 5.6-5.6-5.6-5.6z"),
    IconDef("alert",
        "M12 2 1 21h22L12 2zm0 4.5L19.53 19H4.47L12 6.5zM11 10v5h2v-5h-2zm0 6v2h2v-2h-2z"),
    IconDef("gear",
        "M19.43 12.98a7.46 7.46 0 0 0 0-1.96l2.11-1.65a.5.5 0 0 0 .12-.64l-2-3.46a.5.5 0 0 0-.6-.22l-2.49 1a7.4 7.4 0 0 0-1.69-.98l-.38-2.65A.5.5 0 0 0 14 2h-4a.5.5 0 0 0-.5.42l-.38 2.65c-.61.25-1.18.58-1.69.98l-2.49-1a.5.5 0 0 0-.6.22l-2 3.46a.5.5 0 0 0 .12.64L4.57 11.02a7.46 7.46 0 0 0 0 1.96L2.46 14.63a.5.5 0 0 0-.12.64l2 3.46c.13.22.4.32.6.22l2.49-1c.51.4 1.08.73 1.69.98l.38 2.65c.04.24.25.42.5.42h4c.25 0 .46-.18.5-.42l.38-2.65c.61-.25 1.18-.58 1.69-.98l2.49 1c.2.1.47 0 .6-.22l2-3.46a.5.5 0 0 0-.12-.64l-2.11-1.65zM12 15.5A3.5 3.5 0 1 1 12 8.5a3.5 3.5 0 0 1 0 7z"),
    IconDef("refresh",
        "M12 4V1L8 5l4 4V6a6 6 0 0 1 6 6c0 1.07-.28 2.07-.76 2.94l1.46 1.46A7.93 7.93 0 0 0 20 12a8 8 0 0 0-8-8zm-6 .76A7.93 7.93 0 0 0 4 12a8 8 0 0 0 12.95 6.32L18.41 20A8 8 0 0 1 4 12c0-1.07.28-2.07.76-2.94L4.24 6.62 4 6.76zm5.27 4.51-1.41 1.41L12 13.83 14.14 11.7l-1.41-1.41L12 11.01 9.27 8.28z"),
    IconDef("chevron-down",
        "M7.41 8.59 12 13.17l4.59-4.58L18 10l-6 6-6-6z"),
    IconDef("chevron-up",
        "M7.41 15.41 12 10.83l4.59 4.58L18 14l-6-6-6 6z"),
    IconDef("chevron-right",
        "M9 6l6 6-6 6-1.41-1.41L12.17 12 7.59 7.41z"),
    IconDef("eye",
        "M12 5c-7 0-10 7-10 7s3 7 10 7 10-7 10-7-3-7-10-7zm0 12a5 5 0 1 1 0-10 5 5 0 0 1 0 10zm0-8a3 3 0 1 0 0 6 3 3 0 0 0 0-6z"),
    IconDef("eye-off",
        "M2 4.27 4.28 2 22 19.72 19.73 22l-3.45-3.45A11.06 11.06 0 0 1 12 19c-7 0-10-7-10-7a17.42 17.42 0 0 1 4.07-4.95L2 4.27zM12 7a5 5 0 0 1 5 5c0 .64-.12 1.25-.34 1.82L15.18 12.5A3 3 0 0 0 12 9.5c-.16 0-.32.01-.47.04L9.55 7.55C10.3 7.21 11.13 7 12 7z"),
    IconDef("key",
        "M21 10h-8.35A5.99 5.99 0 0 0 7 6c-3.31 0-6 2.69-6 6s2.69 6 6 6a5.99 5.99 0 0 0 5.65-4H13l2 2 2-2 2 2 4-4.04L21 10zM7 15c-1.65 0-3-1.35-3-3s1.35-3 3-3 3 1.35 3 3-1.35 3-3 3z"),
    IconDef("plus",
        "M19 13h-6v6h-2v-6H5v-2h6V5h2v6h6z"),
    IconDef("trash",
        "M9 3v1H4v2h1v13a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V6h1V4h-5V3H9zm2 5h2v9h-2V8zm-4 0h2v9H7V8zm8 0h2v9h-2V8z"),
    IconDef("undo",
        "M12.5 8c-2.65 0-5.05.99-6.9 2.6L2 7v9h9l-3.62-3.62A7.45 7.45 0 0 1 12.5 11c3.31 0 6.16 1.94 7.5 4.73L22 14.5C20.36 10.83 16.69 8 12.5 8z"),
    IconDef("play",
        "M8 5v14l11-7z"),
    IconDef("pause",
        "M6 5h4v14H6V5zm8 0h4v14h-4V5z"),
    IconDef("logo",
        # The GOLEM eye: a copper circle with an inner dark dot.
        "M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20zm0 4a6 6 0 1 1 0 12 6 6 0 0 1 0-12zm0 3a3 3 0 1 0 0 6 3 3 0 0 0 0-6z"),
    IconDef("spinner",
        # 4-arc ring used for indeterminate loaders.
        "M12 4a8 8 0 1 0 8 8h-2a6 6 0 1 1-6-6V4z"),
    IconDef("arrow-right",
        "M5 12h12.17l-3.58-3.59L15 7l6 6-6 6-1.41-1.41L17.17 14H5z"),
    IconDef("info",
        "M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20zm1 15h-2v-6h2v6zm0-8h-2V7h2v2z"),
    IconDef("warning",
        "M1 21h22L12 2 1 21zm12-3h-2v-2h2v2zm0-4h-2v-4h2v4z"),
    IconDef("document",
        "M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8l-6-6zm-1 7V3.5L18.5 9H13z"),
    IconDef("database",
        "M12 3C7 3 3 4.34 3 6v2c0 1.66 4 3 9 3s9-1.34 9-3V6c0-1.66-4-3-9-3zm0 9c-5 0-9-1.34-9-3v3c0 1.66 4 3 9 3s9-1.34 9-3V9c0 1.66-4 3-9 3zm0 6c-5 0-9-1.34-9-3v3c0 1.66 4 3 9 3s9-1.34 9-3v-3c0 1.66-4 3-9 3z"),
    IconDef("globe",
        "M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20zm-1 17.93A8 8 0 0 1 4.07 13H7c.06 1.62.36 3.13.84 4.45.24.66.53 1.27.87 1.83.13.21.27.4.42.59.07.09.15.16.22.24.13.13.25.27.4.39l.04.04c-.27-.18-.52-.38-.79-.61zM5.7 12c.07-1.62.36-3.13.84-4.45.24-.66.53-1.27.87-1.83.13-.21.27-.4.42-.59.07-.09.15-.16.22-.24.13-.13.25-.27.4-.39l.04-.04c.27.18.52.38.79.61A8 8 0 0 1 11 4.07V7c-.06 1.62-.36 3.13-.84 4.45-.24.66-.53 1.27-.87 1.83-.13.21-.27.4-.42.59-.07.09-.15.16-.22.24-.13.13-.25.27-.4.39l-.04.04A8 8 0 0 1 5.7 12zM12 4.07A8 8 0 0 1 19.93 11H17c-.06-1.62-.36-3.13-.84-4.45a8 8 0 0 1-.87-1.83A8 8 0 0 1 12 4.07zM19.93 13H17c-.06 1.62-.36 3.13-.84 4.45-.24.66-.53 1.27-.87 1.83A8 8 0 0 1 19.93 13z"),
    IconDef("chat",
        "M20 2H4a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h14l4 4V4a2 2 0 0 0-2-2zm-2 12H6v-2h12v2zm0-3H6V9h12v2zm0-3H6V6h12v2z"),
)


# ---------------------------------------------------------------------------
# SVG → PhotoImage renderer
# ---------------------------------------------------------------------------


_PATH_TOKEN_RE = re.compile(r"[MmLlHhVvZzCcCcSsQqQqTtAaHhVv]")


def _parse_svg_path(d: str) -> list[tuple[str, tuple[float, ...]]]:
    """Parse a tiny SVG path string into commands + numeric args.

    Supports M, L, H, V, Z, C, Q (case-sensitive; uppercase = absolute).
    Numbers can be ``1``, ``1.5``, or ``-.5``. Commands can be repeated
    implicitly: ``M10 10 20 20`` is two M/L pairs.
    """
    tokens = re.findall(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?|[MmLlHhVvZzCcQqSsTtAa]", d)
    out: list[tuple[str, tuple[float, ...]]] = []
    i = 0
    n = len(tokens)
    while i < n:
        tk = tokens[i]
        if tk.isalpha():
            cmd = tk
            i += 1
        else:
            # Implicit repeat: M followed by more numbers = L, m followed
            # by more numbers = l.
            cmd = "L" if out and out[-1][0] in "Mm" else "l"
        # Pull args
        args: list[float] = []
        while i < n and not tokens[i].isalpha():
            args.append(float(tokens[i]))
            i += 1
        out.append((cmd, tuple(args)))
    return out


def _draw_path_on_photo(
    img: tk.PhotoImage,
    d: str,
    color: str,
    viewbox: int = 24,
    target_size: int = 16,
    thickness_px: int = 1,
) -> None:
    """Render an SVG path onto a ``PhotoImage`` by computing pixel
    coordinates and ``put()``-ing them. Approximates curves with
    line segments.

    ``viewbox`` is the SVG coordinate system (typically 24). The
    rendered image is ``target_size`` pixels. ``thickness_px`` controls
    stroke thickness in target pixels.

    For curves and round shapes (Z-closed subpaths), we additionally
    run a tiny 4-direction scanline fill so the result looks like a
    solid glyph instead of a thin outline.
    """
    scale = target_size / float(viewbox)
    cmds = _parse_svg_path(d)

    def to_px(x: float, y: float) -> tuple[int, int]:
        return int(round(x * scale)), int(round(y * scale))

    cx, cy = 0.0, 0.0
    subpath: list[tuple[float, float]] = []
    all_subpaths: list[list[tuple[float, float]]] = []
    close_after = False

    for cmd, args in cmds:
        if cmd in ("M", "m"):
            if subpath:
                all_subpaths.append(subpath)
                subpath = []
            x, y = args[0], args[1]
            if cmd == "m" and (cx != 0.0 or cy != 0.0):
                x += cx
                y += cy
            cx, cy = x, y
            subpath.append((cx, cy))
        elif cmd in ("L", "l"):
            x, y = args[0], args[1]
            if cmd == "l":
                x += cx
                y += cy
            cx, cy = x, y
            subpath.append((cx, cy))
        elif cmd in ("H", "h"):
            x = args[0] if cmd == "H" else cx + args[0]
            cx = x
            subpath.append((cx, cy))
        elif cmd in ("V", "v"):
            y = args[0] if cmd == "V" else cy + args[0]
            cy = y
            subpath.append((cx, cy))
        elif cmd in ("Z", "z"):
            close_after = True
            if subpath:
                all_subpaths.append(subpath)
                subpath = []
        elif cmd in ("C", "c"):
            if cmd == "C":
                pts = [(args[0], args[1]), (args[2], args[3]), (args[4], args[5])]
            else:
                pts = [
                    (cx + args[0], cy + args[1]),
                    (cx + args[2], cy + args[3]),
                    (cx + args[4], cy + args[5]),
                ]
            subpath.extend(_cubic_to_points(cx, cy, pts))
            cx, cy = pts[-1]
        elif cmd in ("Q", "q"):
            if cmd == "Q":
                pts = [(args[0], args[1]), (args[2], args[3])]
            else:
                pts = [(cx + args[0], cy + args[1]), (cx + args[2], cy + args[3])]
            subpath.extend(_quad_to_points(cx, cy, pts))
            cx, cy = pts[-1]
        elif cmd in ("A", "a"):
            # Arc: rx, ry, x-axis-rotation, large-arc-flag, sweep-flag, x, y
            rx = args[0] or 1e-9
            ry = args[1] or 1e-9
            x_axis_rotation = args[2]
            large_arc = int(args[3])
            sweep = int(args[4])
            ex, ey = args[5], args[6]
            if cmd == "a":
                ex += cx
                ey += cy
            arc_pts = _arc_to_points(cx, cy, ex, ey, rx, ry, x_axis_rotation, large_arc, sweep)
            subpath.extend(arc_pts)
            cx, cy = ex, ey
        else:
            # Unhandled: silently skip
            pass
    if subpath:
        all_subpaths.append(subpath)

    # Render each subpath as a polyline. For closed subpaths, also do a
    # scanline fill so the shape reads as solid at small sizes.
    width, height = img.width(), img.height()
    for path in all_subpaths:
        if len(path) < 2:
            continue
        pixels: set[tuple[int, int]] = set()
        prev = path[0]
        for pt in path[1:]:
            _line_pixels(prev, pt, pixels, scale)
            prev = pt
        if close_after and path[0] != path[-1]:
            _line_pixels(path[-1], path[0], pixels, scale)
        # Apply thickness by dilating the pixel set.
        if thickness_px > 1:
            pixels = _dilate(pixels, thickness_px)
        for (x, y) in pixels:
            if 0 <= x < width and 0 <= y < height:
                try:
                    img.put(color, (x, y))
                except tk.TclError:
                    return
        # Fill closed subpaths so they look solid.
        if close_after:
            _scanline_fill(img, path, color, scale, width, height)


def _line_pixels(
    p0: tuple[float, float],
    p1: tuple[float, float],
    out: set[tuple[int, int]],
    scale: float,
) -> None:
    """Append integer pixels along a line from p0 to p1 to ``out``.

    Uses Bresenham and rounds target-side coordinates to the integer
    pixel grid, not the SVG grid (so a 24-unit line at scale 16/24
    produces 16 pixels, not 24).
    """
    x0f, y0f = p0[0] * scale, p0[1] * scale
    x1f, y1f = p1[0] * scale, p1[1] * scale
    x0, y0 = int(round(x0f)), int(round(y0f))
    x1, y1 = int(round(x1f)), int(round(y1f))
    dx = abs(x1 - x0)
    dy = -abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx + dy
    while True:
        out.add((x0, y0))
        if x0 == x1 and y0 == y1:
            break
        e2 = 2 * err
        if e2 >= dy:
            err += dy
            x0 += sx
        if e2 <= dx:
            err += dx
            y0 += sy


def _dilate(pixels: set[tuple[int, int]], thickness: int) -> set[tuple[int, int]]:
    """Expand a pixel set by a Manhattan-radius ``thickness``."""
    r = max(1, thickness // 2)
    out: set[tuple[int, int]] = set()
    for (x, y) in pixels:
        for dx in range(-r, r + 1):
            for dy in range(-r, r + 1):
                out.add((x + dx, y + dy))
    return out


def _scanline_fill(
    img: tk.PhotoImage,
    path: list[tuple[float, float]],
    color: str,
    scale: float,
    width: int,
    height: int,
) -> None:
    """Fill the interior of a closed polygon. Even-odd rule. Each scan
    line iterates through the polygon's edges; every pair of crossings
    is filled between."""
    if len(path) < 3:
        return
    # Convert to float pixel coords.
    pts = [(p[0] * scale, p[1] * scale) for p in path]
    ys = [p[1] for p in pts]
    ymin = max(0, int(math.floor(min(ys))))
    ymax = min(height - 1, int(math.ceil(max(ys))))
    if ymax < ymin:
        return
    n = len(pts)
    for y in range(ymin, ymax + 1):
        yf = y + 0.5
        crossings: list[float] = []
        for i in range(n):
            j = (i + 1) % n
            x1, y1 = pts[i]
            x2, y2 = pts[j]
            if (y1 <= yf < y2) or (y2 <= yf < y1):
                if y2 == y1:
                    continue
                t = (yf - y1) / (y2 - y1)
                crossings.append(x1 + t * (x2 - x1))
        crossings.sort()
        for i in range(0, len(crossings) - 1, 2):
            xa = int(math.ceil(crossings[i]))
            xb = int(math.floor(crossings[i + 1]))
            for x in range(max(0, xa), min(width, xb + 1)):
                try:
                    img.put(color, (x, y))
                except tk.TclError:
                    return


def _cubic_to_points(
    x0: float, y0: float,
    ctrl: list[tuple[float, float]],
    segments: int = 12,
) -> list[tuple[float, float]]:
    (x1, y1), (x2, y2), (x3, y3) = ctrl
    out = []
    for i in range(1, segments + 1):
        t = i / segments
        u = 1 - t
        x = u*u*u*x0 + 3*u*u*t*x1 + 3*u*t*t*x2 + t*t*t*x3
        y = u*u*u*y0 + 3*u*u*t*y1 + 3*u*t*t*y2 + t*t*t*y3
        out.append((x, y))
    return out


def _quad_to_points(
    x0: float, y0: float,
    ctrl: list[tuple[float, float]],
    segments: int = 10,
) -> list[tuple[float, float]]:
    (x1, y1), (x2, y2) = ctrl
    out = []
    for i in range(1, segments + 1):
        t = i / segments
        u = 1 - t
        x = u*u*x0 + 2*u*t*x1 + t*t*x2
        y = u*u*y0 + 2*u*t*y1 + t*t*y2
        out.append((x, y))
    return out


def _arc_to_points(
    x1: float, y1: float,
    x2: float, y2: float,
    rx: float, ry: float,
    x_axis_rotation: float,
    large_arc: int,
    sweep: int,
    segments_per_arc: int = 24,
) -> list[tuple[float, float]]:
    """Convert an SVG elliptical arc to a list of polyline points.

    Implementation of the standard W3C SVG arc-to-bezier conversion.
    Reference: https://www.w3.org/TR/SVG/implnote.html#ArcImplementationNotes
    """
    if x1 == x2 and y1 == y2:
        return []
    if rx == 0 or ry == 0:
        return [(x2, y2)]

    rx, ry = abs(rx), abs(ry)
    phi = math.radians(x_axis_rotation % 360.0)
    cos_phi, sin_phi = math.cos(phi), math.sin(phi)

    # Step 1: compute (x1', y1') — coordinates in the rotated frame.
    dx = (x1 - x2) / 2.0
    dy = (y1 - y2) / 2.0
    x1p = cos_phi * dx + sin_phi * dy
    y1p = -sin_phi * dx + cos_phi * dy

    # Step 2: ensure radii are large enough.
    rx_sq, ry_sq = rx * rx, ry * ry
    x1p_sq, y1p_sq = x1p * x1p, y1p * y1p
    radii_check = x1p_sq / rx_sq + y1p_sq / ry_sq
    if radii_check > 1.0:
        s = math.sqrt(radii_check)
        rx *= s
        ry *= s
        rx_sq, ry_sq = rx * rx, ry * ry

    # Step 3: compute (cx', cy') — center in the rotated frame.
    sign = -1 if large_arc == sweep else 1
    numerator = rx_sq * ry_sq - rx_sq * y1p_sq - ry_sq * x1p_sq
    denominator = rx_sq * y1p_sq + ry_sq * x1p_sq
    if denominator == 0:
        return [(x2, y2)]
    sq = max(0.0, numerator / denominator)
    coef = sign * math.sqrt(sq)
    cxp = coef * (rx * y1p / ry)
    cyp = coef * -(ry * x1p / rx)

    # Step 4: compute center (cx, cy) in original frame.
    cx = cos_phi * cxp - sin_phi * cyp + (x1 + x2) / 2.0
    cy = sin_phi * cxp + cos_phi * cyp + (y1 + y2) / 2.0

    # Step 5: compute start angle and delta.
    def angle(ux: float, uy: float, vx: float, vy: float) -> float:
        dot = ux * vx + uy * vy
        length = math.sqrt((ux * ux + uy * uy) * (vx * vx + vy * vy))
        if length == 0:
            return 0.0
        cos_a = max(-1.0, min(1.0, dot / length))
        a = math.acos(cos_a)
        if ux * vy - uy * vx < 0:
            a = -a
        return a

    theta1 = angle(1, 0, (x1p - cxp) / rx, (y1p - cyp) / ry)
    delta_theta = angle(
        (x1p - cxp) / rx, (y1p - cyp) / ry,
        (-x1p - cxp) / rx, (-y1p - cyp) / ry,
    )
    if not sweep and delta_theta > 0:
        delta_theta -= 2 * math.pi
    elif sweep and delta_theta < 0:
        delta_theta += 2 * math.pi

    # Step 6: sample the arc.
    out: list[tuple[float, float]] = []
    total = max(segments_per_arc, int(abs(delta_theta) / (2 * math.pi) * segments_per_arc) + 4)
    for i in range(1, total + 1):
        t = delta_theta * i / total
        cos_t, sin_t = math.cos(theta1 + t), math.sin(theta1 + t)
        # Multiply by rotation matrix
        x = cos_phi * rx * cos_t - sin_phi * ry * sin_t + cx
        y = sin_phi * rx * cos_t + cos_phi * ry * sin_t + cy
        out.append((x, y))
    return out


def _draw_line(
    img: tk.PhotoImage,
    p0: tuple[int, int],
    p1: tuple[int, int],
    color: str,
    thickness: int = 1,
) -> None:
    """Legacy alias — kept so the public API doesn't break, but the
    real work happens in :func:`_draw_path_on_photo` via
    :func:`_line_pixels` + :func:`_dilate` + :func:`_scanline_fill`."""
    _line_pixels(p0, p1, set(), 1.0)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


_CACHE: dict[tuple[str, int, str, int], tk.PhotoImage] = {}


def get_icon(
    name: str,
    size: int | None = None,
    color: str = "#F5F5F7",
    thickness: int = 1,
    master: tk.Misc | None = None,
) -> tk.PhotoImage:
    """Return a ``PhotoImage`` for ``name``.

    ``size`` defaults to ``ICON_SIZE.DEFAULT``. ``master`` is the widget
    the image will be displayed on; when supplied, the image is created
    against that widget's interpreter (not the default root).

    We don't cache. Tk's PhotoImage is small and creating it fresh each
    call is faster than the indirection of maintaining a cache. Each
    call site is expected to keep its own strong reference to the
    returned image.
    """
    if size is None:
        size = ICON_SIZE.DEFAULT
    defn = next((i for i in ICON_LIBRARY if i.name == name), None)
    if master is not None:
        img = tk.PhotoImage(width=size, height=size, master=master)
    else:
        img = tk.PhotoImage(width=size, height=size)
    if defn is not None:
        _draw_path_on_photo(
            img, defn.svg, color, viewbox=24, target_size=size, thickness_px=thickness,
        )
    return img


def _is_still_valid(img: tk.PhotoImage) -> bool:
    """Probe whether a cached image still exists in Tk.

    Kept for the public ``invalidate_cache`` API; unused internally now
    that the cache is disabled.
    """
    try:
        img.tk.call("image", "type", img.name)
    except tk.TclError:
        return False
    return True


def invalidate_cache() -> None:
    """No-op: the icon cache is disabled. Kept for the public API."""
    _CACHE.clear()


def list_icons() -> list[str]:
    """Return the names of all built-in icons."""
    return [i.name for i in ICON_LIBRARY]
