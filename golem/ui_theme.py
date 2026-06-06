"""Design tokens & theme application for the GOLEM launcher UI.

A dark, launcher-inspired palette with orange accent and mono-style
metadata. Background: #0e0e0e. Panels: #151515. Accent: #f97316 (orange
only — no secondary accent colors). Display font: Syne. Metadata/labels:
DM Mono.

Token groups
------------
- ``Colors``     — semantic palette
- ``Spacing``    — 4 px grid scale
- ``Radii``      — corner radius scale
- ``Typography`` — font family + size + weight scale
- ``Motion``     — easing curves + duration scale
- ``Shadows``    — canvas-drawn drop-shadow recipes
- ``IconSize``   — standard icon dimensions
"""
from __future__ import annotations

import tkinter as tk
from dataclasses import dataclass
from tkinter import font as tkfont
from tkinter import ttk
from typing import Any, Literal

# ---------------------------------------------------------------------------
# Color palette — dark launcher theme
# ---------------------------------------------------------------------------
# Single orange accent (#f97316). No copper, no teal, no purple anywhere
# in the accent. Category "why-matched" pills use their own semantic set.


@dataclass(frozen=True, slots=True)
class _Bg:
    canvas: str = "#0a0a0a"          # near-black, deepest layer
    panel: str = "#111111"           # launcher window surface
    elevated: str = "#151515"        # subtle lift
    hover: str = "#1a1a1a"           # item hover state
    selected: str = "#f97316"        # solid orange selected (per spec)
    pressed: str = "#ea580c"         # pressed state
    input: str = "#111111"           # text input fill
    overlay: str = "#080808"         # modal scrim
    titlebar: str = "#0a0a0a"        # window header strip
    sidebar: str = "#121212"         # sidebar panel background


@dataclass(frozen=True, slots=True)
class _Fg:
    primary: str = "#f5f0eb"         # warm white (not pure white — per spec)
    secondary: str = "#7a7370"       # metadata, paths, timestamps
    tertiary: str = "#3d3a38"        # dividers, muted text
    disabled: str = "#404040"        # disabled
    on_accent: str = "#ffffff"       # white text on orange selected
    inverse: str = "#0a0a0b"         # dark text on light surface


@dataclass(frozen=True, slots=True)
class _Accent:
    """Single orange #f97316 — no other accent colors anywhere."""
    DEFAULT: str = "#f97316"         # primary orange
    hover: str = "#fb923c"           # lighter orange
    pressed: str = "#ea580c"         # deeper orange
    muted: str = "#431407"           # very dark orange (15% opacity bg)
    glow: str = "#f9731626"           # 15% alpha for focus rings (hex)
    ring: str = "#f9731680"           # 50% alpha for focus ring borders
    dim: str = "#f9731680"            # subtle orange elements (50% alpha)
    glow_border: str = "#f97316"     # search bar focus glow match


@dataclass(frozen=True, slots=True)
class _Border:
    subtle: str = "#151515"           # internal dividers
    DEFAULT: str = "#1a1a1a"          # standard divider
    strong: str = "#222222"           # emphasized divider
    focus: str = "#f97316"            # focus ring (orange)


@dataclass(frozen=True, slots=True)
class _State:
    success: str = "#22c55e"         # green
    success_muted: str = "#0a2e1a"
    warning: str = "#eab308"         # yellow
    warning_muted: str = "#2e220a"
    error: str = "#ef4444"           # red
    error_muted: str = "#2e0a0a"
    info: str = "#3b82f6"            # blue
    info_muted: str = "#0a1a2e"


@dataclass(frozen=True, slots=True)
class _Category:
    """Minimal category differentiation — kept subdued to not compete."""
    finance: str = "#22c55e"
    research: str = "#3b82f6"
    design: str = "#f97316"
    code: str = "#a855f7"
    media: str = "#ec4899"
    personal: str = "#eab308"
    legal: str = "#6b7280"
    other: str = "#606060"


@dataclass(frozen=True, slots=True)
class Colors:
    bg: _Bg = _Bg()
    fg: _Fg = _Fg()
    accent: _Accent = _Accent()
    border: _Border = _Border()
    state: _State = _State()
    category: _Category = _Category()


# ---------------------------------------------------------------------------
# Spacing — 4 px grid
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Spacing:
    xxs: int = 2
    xs: int = 4
    sm: int = 8
    md: int = 12
    lg: int = 16
    xl: int = 20
    xxl: int = 24
    xxxl: int = 32
    gutter: int = 18      # standard window edge padding


# ---------------------------------------------------------------------------
# Radii — sharp, launcher-style
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Radii:
    none: int = 0
    sm: int = 4
    DEFAULT: int = 8      # the standard corner (slightly larger)
    md: int = 10
    lg: int = 12
    pill: int = 999       # for circular chips


# ---------------------------------------------------------------------------
# Typography — Syne for display, DM Mono for metadata/labels
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _TypeScale:
    family: str
    size: int
    weight: Literal["normal", "bold"] = "normal"
    line_height: int = 0   # 0 = computed as 1.4 * size

    def font(self) -> tuple[str, int, str]:
        return (self.family, self.size, self.weight)


@dataclass(frozen=True, slots=True)
class Typography:
    # Display: Syne (Google Font). Falls back to Segoe UI / system sans.
    display_family: str = "Syne"
    # Metadata & labels: DM Mono (Google Font). Falls back to Consolas.
    mono_family: str = "DM Mono"
    # UI sans fallback
    sans: str = "Segoe UI"
    # Monospace fallback
    mono: str = "Consolas"

    # Scale — display uses Syne, everything else uses system sans with
    # DM Mono for metadata/labels
    display: _TypeScale = _TypeScale("Syne", 22, "bold", 30)
    title: _TypeScale = _TypeScale("Syne", 16, "bold", 22)
    body: _TypeScale = _TypeScale("Segoe UI", 14, "normal", 20)
    body_strong: _TypeScale = _TypeScale("Segoe UI", 14, "bold", 20)
    caption: _TypeScale = _TypeScale("DM Mono", 11, "normal", 16)    # DM Mono for labels
    micro: _TypeScale = _TypeScale("DM Mono", 10, "normal", 14)      # DM Mono for tiny labels
    code: _TypeScale = _TypeScale("DM Mono", 11, "normal", 16)
    kbd: _TypeScale = _TypeScale("DM Mono", 10, "normal", 14)
    pill: _TypeScale = _TypeScale("DM Mono", 9, "normal", 12)        # DM Mono for pills


# ---------------------------------------------------------------------------
# Motion
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Motion:
    instant: int = 60
    fast: int = 120
    DEFAULT: int = 200
    slow: int = 320
    max: int = 480
    reduced_motion: bool = False


# ---------------------------------------------------------------------------
# Shadow recipes
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _ShadowStep:
    color: str
    radius: int
    offset_y: int


@dataclass(frozen=True, slots=True)
class Shadows:
    popover: tuple[_ShadowStep, ...] = (
        _ShadowStep("#00000060", 32, 16),
        _ShadowStep("#00000080", 16, 8),
        _ShadowStep("#000000a0", 8, 4),
    )
    dialog: tuple[_ShadowStep, ...] = (
        _ShadowStep("#00000060", 48, 28),
        _ShadowStep("#00000080", 28, 12),
        _ShadowStep("#000000a0", 14, 6),
    )
    chip: tuple[_ShadowStep, ...] = (
        _ShadowStep("#00000060", 4, 1),
    )
    glow: tuple[_ShadowStep, ...] = (
        _ShadowStep("#f9731633", 16, 0),
        _ShadowStep("#f973161a", 8, 0),
    )
    card: tuple[_ShadowStep, ...] = (
        _ShadowStep("#00000040", 12, 4),
        _ShadowStep("#00000060", 4, 2),
    )
    card_hover: tuple[_ShadowStep, ...] = (
        _ShadowStep("#f973161a", 16, 6),
        _ShadowStep("#00000060", 8, 4),
    )
    surface: tuple[_ShadowStep, ...] = (
        _ShadowStep("#00000030", 6, 2),
    )


# ---------------------------------------------------------------------------
# Icon sizes
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class IconSize:
    micro: int = 10
    sm: int = 12
    DEFAULT: int = 14
    md: int = 16
    lg: int = 20
    xl: int = 24
    sidebar: int = 18


# ---------------------------------------------------------------------------
# Gradients — subtle overlay helpers
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Gradient:
    """Pre-defined gradient values for canvas-drawn overlays."""
    accent_to_transparent: str = "#f97316"  # use with create_linear_gradient
    panel_to_dark: str = "#151515"
    elevated_to_dark: str = "#1a1a1a"


# GRADIENT is reserved for future gradient overlay use


# ---------------------------------------------------------------------------
# Z-index layers
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Z:
    scrim: str = "scrim"
    popover: str = "popover"
    dialog: str = "dialog"
    toast: str = "toast"
    sidebar: str = "sidebar"


# ---------------------------------------------------------------------------
# Sizing — launcher proportions
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Size:
    row_height: int = 56               # taller result items for launcher feel
    row_height_compact: int = 44
    input_height: int = 52             # search box height per spec
    button_height: int = 36
    button_height_sm: int = 28
    icon_button: int = 32
    titlebar_height: int = 36
    statusbar_height: int = 32         # footer bar height per spec
    search_popup_w: int = 640          # fixed width per spec
    search_popup_h: int = 560          # max height per spec
    search_popup_min_h: int = 200
    onboarding_w: int = 640
    onboarding_h: int = 720


# ---------------------------------------------------------------------------
# Singleton accessors
# ---------------------------------------------------------------------------

COLORS = Colors()
SPACING = Spacing()
RADII = Radii()
TYPOGRAPHY = Typography()
MOTION = Motion()
SHADOWS = Shadows()
GRADIENT = Gradient()
ICON_SIZE = IconSize()
SIZE = Size()
Z_LAYERS = Z()


# ---------------------------------------------------------------------------
# ttk Style application
# ---------------------------------------------------------------------------


def _make_named_font(slot: _TypeScale) -> tkfont.Font:
    name = f"golem.{slot.family}.{slot.size}.{slot.weight}"
    if name in tkfont.names():
        tkfont.nametofont(name).configure(
            family=slot.family, size=slot.size, weight=slot.weight
        )
        return tkfont.nametofont(name)
    f = tkfont.Font(name=name, family=slot.family, size=slot.size, weight=slot.weight)
    return f


def describe() -> dict[str, Any]:
    """Return a snapshot of the active tokens."""
    return {
        "colors": {
            "bg.canvas": COLORS.bg.canvas,
            "bg.panel": COLORS.bg.panel,
            "accent": COLORS.accent.DEFAULT,
            "border.subtle": COLORS.border.subtle,
            "fg.primary": COLORS.fg.primary,
        },
        "spacing": {"sm": SPACING.sm, "md": SPACING.md, "lg": SPACING.lg},
        "radii": {"default": RADII.DEFAULT},
        "typography": {
            "display": TYPOGRAPHY.display.font(),
            "body": TYPOGRAPHY.body.font(),
            "caption": TYPOGRAPHY.caption.font(),
        },
    }


def apply_theme(root: tk.Misc) -> None:
    """Configure ttk styles for the entire app. Call once on the root."""
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass

    # Register named fonts
    for slot in (
        TYPOGRAPHY.display,
        TYPOGRAPHY.title,
        TYPOGRAPHY.body,
        TYPOGRAPHY.body_strong,
        TYPOGRAPHY.caption,
        TYPOGRAPHY.micro,
        TYPOGRAPHY.code,
        TYPOGRAPHY.kbd,
        TYPOGRAPHY.pill,
    ):
        _make_named_font(slot)

    # -- Base
    style.configure(".",
        background=COLORS.bg.panel,
        foreground=COLORS.fg.primary,
        fieldbackground=COLORS.bg.input,
        bordercolor=COLORS.border.DEFAULT,
        lightcolor=COLORS.bg.panel,
        darkcolor=COLORS.bg.panel,
        troughcolor=COLORS.bg.canvas,
        font=TYPOGRAPHY.body.font(),
        borderwidth=0,
        focusthickness=0)

    # -- Frame
    style.configure("TFrame", background=COLORS.bg.panel)
    style.configure("Canvas.TFrame", background=COLORS.bg.panel)
    style.configure("Row.TFrame", background=COLORS.bg.elevated)
    style.configure("RowHover.TFrame", background=COLORS.bg.hover)
    style.configure("RowSelected.TFrame", background=COLORS.bg.selected)
    style.configure("Titlebar.TFrame", background=COLORS.bg.titlebar)
    style.configure("Sidebar.TFrame", background=COLORS.bg.sidebar)

    # -- Label
    style.configure("TLabel", background=COLORS.bg.panel, foreground=COLORS.fg.primary)
    style.configure("Title.TLabel", background=COLORS.bg.panel, foreground=COLORS.fg.primary,
                    font=TYPOGRAPHY.title.font())
    style.configure("Display.TLabel", background=COLORS.bg.panel, foreground=COLORS.fg.primary,
                    font=TYPOGRAPHY.display.font())
    style.configure("Body.TLabel", background=COLORS.bg.panel, foreground=COLORS.fg.primary,
                    font=TYPOGRAPHY.body.font())
    style.configure("BodyStrong.TLabel", background=COLORS.bg.panel, foreground=COLORS.fg.primary,
                    font=TYPOGRAPHY.body_strong.font())
    style.configure("Caption.TLabel", background=COLORS.bg.panel, foreground=COLORS.fg.secondary,
                    font=TYPOGRAPHY.caption.font())
    style.configure("Micro.TLabel", background=COLORS.bg.panel, foreground=COLORS.fg.tertiary,
                    font=TYPOGRAPHY.micro.font())
    style.configure("Kbd.TLabel", background=COLORS.bg.elevated, foreground=COLORS.fg.secondary,
                    font=TYPOGRAPHY.kbd.font())
    style.configure("Pill.TLabel", background=COLORS.bg.elevated, foreground=COLORS.fg.secondary,
                    font=TYPOGRAPHY.pill.font())
    style.configure("Success.TLabel", background=COLORS.bg.panel, foreground=COLORS.state.success)
    style.configure("Error.TLabel", background=COLORS.bg.panel, foreground=COLORS.state.error)
    style.configure("Warning.TLabel", background=COLORS.bg.panel, foreground=COLORS.state.warning)

    # -- Button
    style.configure("TButton",
        background=COLORS.bg.elevated,
        foreground=COLORS.fg.primary,
        bordercolor=COLORS.border.DEFAULT,
        borderwidth=1, focusthickness=0, relief="flat",
        padding=(SPACING.md, SPACING.xs),
        font=TYPOGRAPHY.body.font())
    style.map("TButton",
        background=[("active", COLORS.bg.hover), ("pressed", COLORS.bg.pressed),
                    ("disabled", COLORS.bg.panel)],
        foreground=[("disabled", COLORS.fg.disabled)],
        bordercolor=[("focus", COLORS.border.focus)])

    style.configure("Primary.TButton",
        background=COLORS.accent.DEFAULT,
        foreground=COLORS.fg.on_accent,
        bordercolor=COLORS.accent.DEFAULT,
        borderwidth=1, relief="flat",
        padding=(SPACING.xl, SPACING.sm),
        font=TYPOGRAPHY.body_strong.font())
    style.map("Primary.TButton",
        background=[("active", COLORS.accent.hover), ("pressed", COLORS.accent.pressed),
                    ("disabled", COLORS.accent.muted)],
        foreground=[("disabled", COLORS.fg.disabled)],
        bordercolor=[("focus", COLORS.accent.ring)])

    style.configure("Ghost.TButton",
        background=COLORS.bg.panel,
        foreground=COLORS.fg.secondary,
        bordercolor=COLORS.border.subtle,
        borderwidth=1, relief="flat",
        padding=(SPACING.md, SPACING.xs),
        font=TYPOGRAPHY.body.font())
    style.map("Ghost.TButton",
        background=[("active", COLORS.bg.hover), ("pressed", COLORS.bg.pressed)],
        foreground=[("active", COLORS.fg.primary)])

    # -- Entry (search bar)
    style.configure("TEntry",
        fieldbackground=COLORS.bg.input,
        foreground=COLORS.fg.primary,
        insertcolor=COLORS.accent.DEFAULT,
        bordercolor=COLORS.border.DEFAULT,
        lightcolor=COLORS.bg.input,
        darkcolor=COLORS.bg.input,
        borderwidth=1, relief="flat",
        padding=(SPACING.sm, SPACING.sm))
    style.map("TEntry",
        bordercolor=[("focus", COLORS.accent.DEFAULT)],
        lightcolor=[("focus", COLORS.bg.input)],
        darkcolor=[("focus", COLORS.bg.input)])

    # -- SearchBar.TEntry — special entry for the search popup with orange glow
    style.configure("SearchBar.TEntry",
        fieldbackground=COLORS.bg.input,
        foreground=COLORS.fg.primary,
        insertcolor=COLORS.accent.DEFAULT,
        bordercolor=COLORS.border.DEFAULT,
        lightcolor=COLORS.bg.input,
        darkcolor=COLORS.bg.input,
        borderwidth=1, relief="flat",
        padding=(SPACING.md, SPACING.sm))
    style.map("SearchBar.TEntry",
        bordercolor=[("focus", COLORS.accent.glow_border)],
        lightcolor=[("focus", COLORS.bg.input)],
        darkcolor=[("focus", COLORS.bg.input)])

    # -- Scrollbar
    style.configure("Vertical.TScrollbar",
        background=COLORS.bg.panel,
        troughcolor=COLORS.bg.panel,
        bordercolor=COLORS.bg.panel,
        arrowcolor=COLORS.fg.tertiary,
        gripcount=0, borderwidth=0, relief="flat", width=6)
    style.map("Vertical.TScrollbar",
        background=[("active", COLORS.bg.hover), ("pressed", COLORS.bg.pressed)])

    # -- Separator
    style.configure("TSeparator", background=COLORS.border.subtle)

    # -- tk-level option defaults
    try:
        root.option_add("*Menu*Background", COLORS.bg.elevated)
        root.option_add("*Menu*Foreground", COLORS.fg.primary)
        root.option_add("*Menu*selectColor", COLORS.fg.primary)
        root.option_add("*Menu*activeBackground", COLORS.bg.hover)
        root.option_add("*Menu*activeForeground", COLORS.fg.primary)
        root.option_add("*Menu*relief", "flat")
        root.option_add("*Menu*borderWidth", 0)
    except tk.TclError:
        pass


# ---------------------------------------------------------------------------
# Easing curves
# ---------------------------------------------------------------------------


def ease_out_cubic(t: float) -> float:
    if t <= 0.0: return 0.0
    if t >= 1.0: return 1.0
    inv = 1.0 - t
    return 1.0 - inv * inv * inv


def ease_in_cubic(t: float) -> float:
    if t <= 0.0: return 0.0
    if t >= 1.0: return 1.0
    return t * t * t


def ease_in_out_cubic(t: float) -> float:
    if t <= 0.0: return 0.0
    if t >= 1.0: return 1.0
    if t < 0.5: return 4.0 * t * t * t
    f = 2.0 * t - 2.0
    return 0.5 * f * f * f + 1.0


def ease_out_back(t: float, s: float = 1.70158) -> float:
    if t <= 0.0: return 0.0
    if t >= 1.0: return 1.0
    f = t - 1.0
    return f * f * ((s + 1.0) * f + s) + 1.0


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def lerp_color(c1: str, c2: str, t: float) -> str:
    a = _parse_hex(c1)
    b = _parse_hex(c2)
    return f"#{int(lerp(a[0], b[0], t)):02X}{int(lerp(a[1], b[1], t)):02X}{int(lerp(a[2], b[2], t)):02X}"


def _parse_hex(c: str) -> tuple[int, int, int]:
    c = c.lstrip("#")
    if len(c) == 3:
        c = "".join(ch * 2 for ch in c)
    return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)
