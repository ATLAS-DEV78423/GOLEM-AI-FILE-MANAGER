"""Design tokens & theme application for the GOLEM UI.

A Raycast-inspired palette: deep layered blacks, a warm copper/amber
accent, monospace hints, sharp 6 px corners. Every widget reads from
this module — no hex literals in component code.

Token groups
------------
- ``Colors``     — semantic palette. ``Colors.bg.canvas`` etc.
- ``Spacing``    — 4 px grid scale.
- ``Radii``      — corner radius scale.
- ``Typography`` — font family + size + weight scale.
- ``Motion``     — easing curves + duration scale.
- ``Shadows``    — canvas-drawn drop-shadow recipes.
- ``IconSize``   — standard icon dimensions.
- ``Z``          — z-index layers.

Usage
-----
::

    from .ui_theme import Colors, Spacing, Typography, apply_theme

    root = tk.Tk()
    apply_theme(root)
    label = tk.Label(root, text="hello", bg=Colors.bg.elevated, fg=Colors.fg.primary,
                     font=Typography.body.font())
"""
from __future__ import annotations

import tkinter as tk
from dataclasses import dataclass
from tkinter import font as tkfont
from tkinter import ttk
from typing import Any, Literal


# ---------------------------------------------------------------------------
# Color palette
# ---------------------------------------------------------------------------
# Naming convention: ``bg.*`` for surfaces, ``fg.*`` for text, ``accent.*``
# for the brand color, ``border.*`` for separators, ``state.*`` for feedback.


@dataclass(frozen=True, slots=True)
class _Bg:
    """Surface colors, darkest to lightest."""

    canvas: str = "#0A0A0B"          # the page
    panel: str = "#101012"           # cards, popup body
    elevated: str = "#16161A"        # rows, list items
    hover: str = "#1C1C22"           # row hover
    selected: str = "#26262E"        # row selected
    pressed: str = "#2E2E38"         # row / button pressed
    input: str = "#0D0D10"           # text input fill
    overlay: str = "#050507"         # modal scrim
    titlebar: str = "#08080A"        # window header strip


@dataclass(frozen=True, slots=True)
class _Fg:
    """Foreground / text colors, highest to lowest emphasis."""

    primary: str = "#F5F5F7"         # default body
    secondary: str = "#B8B8C0"       # muted
    tertiary: str = "#7A7A85"        # hints
    disabled: str = "#4A4A52"        # disabled
    on_accent: str = "#0A0A0B"       # text on copper buttons
    inverse: str = "#0A0A0B"         # dark text on light surface (unused but defined)


@dataclass(frozen=True, slots=True)
class _Accent:
    """Brand copper/amber accent."""

    DEFAULT: str = "#FF8C42"         # primary
    hover: str = "#FFA15E"           # hover
    pressed: str = "#E0731F"         # pressed
    muted: str = "#5A2F0F"           # row indicator dot, subdued
    glow: str = "#FF8C4233"           # 20% alpha, for focus rings
    ring: str = "#FF8C4280"           # 50% alpha, focus ring border
    dim: str = "#3A1E08"             # chip background, very subdued


@dataclass(frozen=True, slots=True)
class _Border:
    """Separator colors."""

    subtle: str = "#1F1F25"          # hairline divider
    DEFAULT: str = "#2A2A32"         # standard divider
    strong: str = "#3A3A45"          # emphasized divider
    focus: str = "#FF8C42"           # focus ring


@dataclass(frozen=True, slots=True)
class _State:
    """Semantic feedback colors (kept restrained)."""

    success: str = "#5DD39E"         # green
    success_muted: str = "#1F3D2E"
    warning: str = "#FFB454"         # amber (close to accent — intentional)
    warning_muted: str = "#3D2A14"
    error: str = "#FF5C5C"           # red
    error_muted: str = "#3D1A1A"
    info: str = "#7BB8FF"            # blue
    info_muted: str = "#15243D"


@dataclass(frozen=True, slots=True)
class _Category:
    """Per-category accent for search result chips.

    Not a real full palette — just enough to distinguish the 8 categories
    in a result list without competing with the brand copper.
    """

    finance: str = "#5DD39E"
    research: str = "#7BB8FF"
    design: str = "#FF8C42"
    code: str = "#B98CFF"
    media: str = "#FF6E9C"
    personal: str = "#FFD66B"
    legal: str = "#9AA0A8"
    other: str = "#7A7A85"


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
# Radii — sharp, Raycast-style
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Radii:
    none: int = 0
    sm: int = 4
    DEFAULT: int = 6     # the standard corner
    md: int = 8
    lg: int = 10
    pill: int = 999       # for circular chips


# ---------------------------------------------------------------------------
# Typography
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _TypeScale:
    """A single type slot: family, size, weight, line-height (px)."""

    family: str
    size: int
    weight: Literal["normal", "bold"] = "normal"
    line_height: int = 0   # 0 = computed as 1.4 * size
    tracking: int = 0      # letter-spacing in 1/1000 em (Tk doesn't expose; we approximate with spaces)

    def font(self) -> tuple[str, int, str]:
        return (self.family, self.size, self.weight)


@dataclass(frozen=True, slots=True)
class Typography:
    # UI sans family — Segoe UI Variable on Windows 11, Segoe UI elsewhere.
    sans: str = "Segoe UI"
    # Monospace — Consolas on Windows, Menlo on macOS. Used for keyboard
    # hints and file paths.
    mono: str = "Consolas"

    # Scale
    display: _TypeScale = _TypeScale("Segoe UI", 24, "bold", 32)
    title: _TypeScale = _TypeScale("Segoe UI", 17, "bold", 24)
    body: _TypeScale = _TypeScale("Segoe UI", 14, "normal", 20)
    body_strong: _TypeScale = _TypeScale("Segoe UI", 14, "bold", 20)
    caption: _TypeScale = _TypeScale("Segoe UI", 12, "normal", 18)
    micro: _TypeScale = _TypeScale("Segoe UI", 11, "normal", 16)
    code: _TypeScale = _TypeScale("Consolas", 11, "normal", 16)
    kbd: _TypeScale = _TypeScale("Consolas", 10, "normal", 14)


# ---------------------------------------------------------------------------
# Motion
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Motion:
    """Duration + easing. Durations in ms.

    Easing curves are pre-computed lookup tables expressed as
    ``(input_t, output_t)`` tuples for the animation primitives. We use
    cubic-out and back-out for entry, cubic-in for exit, cubic-in-out
    for state changes.
    """

    instant: int = 60
    fast: int = 120
    DEFAULT: int = 200
    slow: int = 320
    max: int = 480

    # Reduced-motion fallback. When set, animations should snap to final
    # state in ``instant`` ms. UI reads this to decide.
    reduced_motion: bool = False


# ---------------------------------------------------------------------------
# Shadow recipes (canvas-drawn, not real blur — faked with stacked rects)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _ShadowStep:
    color: str
    radius: int
    offset_y: int


@dataclass(frozen=True, slots=True)
class Shadows:
    """Faked drop-shadows drawn with overlapping rects. Cheap, no PIL.

    ``popover`` is the 6-step stack used on the search popup. ``dialog``
    is heavier for the onboarding wizard. ``chip`` is a 1-px ring for
    result rows.
    """

    popover: tuple[_ShadowStep, ...] = (
        _ShadowStep("#00000040", 24, 12),
        _ShadowStep("#00000060", 16, 6),
        _ShadowStep("#00000080", 8, 2),
    )
    dialog: tuple[_ShadowStep, ...] = (
        _ShadowStep("#00000050", 40, 24),
        _ShadowStep("#00000070", 24, 10),
        _ShadowStep("#00000090", 12, 4),
    )
    chip: tuple[_ShadowStep, ...] = (
        _ShadowStep("#00000060", 4, 1),
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


# ---------------------------------------------------------------------------
# Z-index layers (Tk raise/lower is string-based, but a vocabulary helps)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Z:
    scrim: str = "scrim"
    popover: str = "popover"
    dialog: str = "dialog"
    toast: str = "toast"
    menu: str = "menu"


# ---------------------------------------------------------------------------
# Sizing
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Size:
    """Common widget sizes (in px)."""

    row_height: int = 44
    row_height_compact: int = 32
    input_height: int = 36
    button_height: int = 36
    button_height_sm: int = 28
    icon_button: int = 32
    titlebar_height: int = 36
    statusbar_height: int = 26
    search_popup_w: int = 620
    search_popup_h: int = 480
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
ICON_SIZE = IconSize()
SIZE = Size()
Z_LAYERS = Z()


# ---------------------------------------------------------------------------
# ttk Style application
# ---------------------------------------------------------------------------


def _make_named_font(slot: _TypeScale) -> tkfont.Font:
    """Create a named Tk font for a type slot. Idempotent — re-calling
    replaces the font with new settings."""
    name = f"golem.{slot.family}.{slot.size}.{slot.weight}"
    if name in tkfont.names():
        tkfont.nametofont(name).configure(
            family=slot.family, size=slot.size, weight=slot.weight
        )
        return tkfont.nametofont(name)
    f = tkfont.Font(name=name, family=slot.family, size=slot.size, weight=slot.weight)
    return f


def apply_theme(root: tk.Misc) -> None:
    """Configure ttk styles for the entire app. Call once on the root.

    Styles defined:
      - TFrame, TLabel, TButton, TEntry, TCombobox, TCheckbutton, TProgressbar,
        TScrollbar, TNotebook.* — themed to match the Raycast palette.
      - "Primary.TButton" — copper accent.
      - "Ghost.TButton"   — transparent with hover.
      - "Row.TFrame"      — list row container.
      - "Title.TLabel"    — page title.
      - "Caption.TLabel"  — muted small text.
    """
    style = ttk.Style(root)
    # "clam" is the only theme whose colors we can override for everything.
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass

    # Register the named fonts
    for slot in (
        TYPOGRAPHY.display,
        TYPOGRAPHY.title,
        TYPOGRAPHY.body,
        TYPOGRAPHY.body_strong,
        TYPOGRAPHY.caption,
        TYPOGRAPHY.micro,
        TYPOGRAPHY.code,
        TYPOGRAPHY.kbd,
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
    style.configure("Inverse.TLabel", background=COLORS.bg.panel, foreground=COLORS.fg.secondary)
    style.configure("Success.TLabel", background=COLORS.bg.panel, foreground=COLORS.state.success)
    style.configure("Error.TLabel", background=COLORS.bg.panel, foreground=COLORS.state.error)
    style.configure("Warning.TLabel", background=COLORS.bg.panel, foreground=COLORS.state.warning)

    # -- Button
    style.configure("TButton",
                    background=COLORS.bg.elevated,
                    foreground=COLORS.fg.primary,
                    bordercolor=COLORS.border.DEFAULT,
                    borderwidth=1,
                    focusthickness=0,
                    relief="flat",
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
                    borderwidth=1,
                    relief="flat",
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
                    borderwidth=1,
                    relief="flat",
                    padding=(SPACING.md, SPACING.xs),
                    font=TYPOGRAPHY.body.font())
    style.map("Ghost.TButton",
              background=[("active", COLORS.bg.hover), ("pressed", COLORS.bg.pressed)],
              foreground=[("active", COLORS.fg.primary)])

    style.configure("Icon.TButton",
                    background=COLORS.bg.panel,
                    foreground=COLORS.fg.secondary,
                    bordercolor=COLORS.border.subtle,
                    borderwidth=1,
                    relief="flat",
                    padding=(SPACING.xs, SPACING.xs),
                    font=TYPOGRAPHY.body.font(),
                    width=2)
    style.map("Icon.TButton",
              background=[("active", COLORS.bg.hover), ("pressed", COLORS.bg.pressed)],
              foreground=[("active", COLORS.fg.primary)])

    # -- Entry
    style.configure("TEntry",
                    fieldbackground=COLORS.bg.input,
                    foreground=COLORS.fg.primary,
                    insertcolor=COLORS.accent.DEFAULT,
                    bordercolor=COLORS.border.DEFAULT,
                    lightcolor=COLORS.bg.input,
                    darkcolor=COLORS.bg.input,
                    borderwidth=1,
                    relief="flat",
                    padding=(SPACING.sm, SPACING.sm))
    style.map("TEntry",
              bordercolor=[("focus", COLORS.accent.DEFAULT)],
              lightcolor=[("focus", COLORS.bg.input)],
              darkcolor=[("focus", COLORS.bg.input)])

    style.configure("Secret.TEntry",
                    fieldbackground=COLORS.bg.input,
                    foreground=COLORS.fg.primary,
                    insertcolor=COLORS.accent.DEFAULT,
                    bordercolor=COLORS.border.DEFAULT,
                    lightcolor=COLORS.bg.input,
                    darkcolor=COLORS.bg.input,
                    borderwidth=1,
                    relief="flat",
                    padding=(SPACING.sm, SPACING.sm))

    # -- Combobox
    style.configure("TCombobox",
                    fieldbackground=COLORS.bg.input,
                    background=COLORS.bg.input,
                    foreground=COLORS.fg.primary,
                    arrowcolor=COLORS.fg.secondary,
                    bordercolor=COLORS.border.DEFAULT,
                    lightcolor=COLORS.bg.input,
                    darkcolor=COLORS.bg.input,
                    borderwidth=1,
                    relief="flat",
                    padding=(SPACING.sm, SPACING.xs))
    style.map("TCombobox",
              fieldbackground=[("readonly", COLORS.bg.input)],
              foreground=[("readonly", COLORS.fg.primary)],
              bordercolor=[("focus", COLORS.accent.DEFAULT)])
    # The dropdown listbox is styled separately (option_add below).

    # -- Checkbutton
    style.configure("TCheckbutton",
                    background=COLORS.bg.panel,
                    foreground=COLORS.fg.primary,
                    focuscolor=COLORS.bg.panel,
                    font=TYPOGRAPHY.body.font(),
                    padding=(SPACING.xs, SPACING.xs))
    style.map("TCheckbutton",
              background=[("active", COLORS.bg.panel)],
              foreground=[("disabled", COLORS.fg.disabled)],
              indicatorcolor=[("selected", COLORS.accent.DEFAULT),
                              ("!selected", COLORS.bg.input)],
              indicatormargin=[("!selected", 4)])

    # -- Progressbar (determinate, used in the titlebar scan meter)
    style.configure("TProgressbar",
                    background=COLORS.accent.DEFAULT,
                    troughcolor=COLORS.bg.canvas,
                    bordercolor=COLORS.bg.canvas,
                    lightcolor=COLORS.accent.DEFAULT,
                    darkcolor=COLORS.accent.DEFAULT,
                    borderwidth=0)
    style.configure("Indeterminate.TProgressbar",
                    background=COLORS.accent.DEFAULT,
                    troughcolor=COLORS.bg.canvas,
                    bordercolor=COLORS.bg.canvas,
                    lightcolor=COLORS.accent.DEFAULT,
                    darkcolor=COLORS.accent.DEFAULT,
                    borderwidth=0)

    # -- Scrollbar
    style.configure("Vertical.TScrollbar",
                    background=COLORS.bg.panel,
                    troughcolor=COLORS.bg.panel,
                    bordercolor=COLORS.bg.panel,
                    arrowcolor=COLORS.fg.tertiary,
                    gripcount=0,
                    borderwidth=0,
                    relief="flat",
                    width=8)
    style.map("Vertical.TScrollbar",
              background=[("active", COLORS.bg.hover), ("pressed", COLORS.bg.pressed)])
    style.configure("Horizontal.TScrollbar",
                    background=COLORS.bg.panel,
                    troughcolor=COLORS.bg.panel,
                    bordercolor=COLORS.bg.panel,
                    arrowcolor=COLORS.fg.tertiary,
                    gripcount=0,
                    borderwidth=0,
                    relief="flat",
                    height=8)
    style.map("Horizontal.TScrollbar",
              background=[("active", COLORS.bg.hover), ("pressed", COLORS.bg.pressed)])

    # -- Separator
    style.configure("TSeparator", background=COLORS.border.subtle)

    # -- Notebook (steps in onboarding)
    style.configure("TNotebook", background=COLORS.bg.panel, borderwidth=0)
    style.configure("TNotebook.Tab",
                    background=COLORS.bg.panel,
                    foreground=COLORS.fg.tertiary,
                    padding=(SPACING.md, SPACING.xs),
                    font=TYPOGRAPHY.caption.font())
    style.map("TNotebook.Tab",
              background=[("selected", COLORS.bg.panel)],
              foreground=[("selected", COLORS.fg.primary)])

    # -- tk-level option defaults for popup listboxes, etc.
    try:
        root.option_add("*TCombobox*Listbox*Background", COLORS.bg.elevated)
        root.option_add("*TCombobox*Listbox*Foreground", COLORS.fg.primary)
        root.option_add("*TCombobox*Listbox*selectBackground", COLORS.accent.muted)
        root.option_add("*TCombobox*Listbox*selectForeground", COLORS.fg.primary)
        root.option_add("*TCombobox*Listbox*Font", TYPOGRAPHY.body.font())
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
    """1 - (1 - t)^3 — sharp deceleration. Good for entry animations."""
    if t <= 0.0:
        return 0.0
    if t >= 1.0:
        return 1.0
    inv = 1.0 - t
    return 1.0 - inv * inv * inv


def ease_in_cubic(t: float) -> float:
    """t^3 — sharp acceleration. Good for exit animations."""
    if t <= 0.0:
        return 0.0
    if t >= 1.0:
        return 1.0
    return t * t * t


def ease_in_out_cubic(t: float) -> float:
    """Smooth both ends. Good for state-change transitions."""
    if t <= 0.0:
        return 0.0
    if t >= 1.0:
        return 1.0
    if t < 0.5:
        return 4.0 * t * t * t
    f = 2.0 * t - 2.0
    return 0.5 * f * f * f + 1.0


def ease_out_back(t: float, s: float = 1.70158) -> float:
    """Slight overshoot. Good for popovers and toasts."""
    if t <= 0.0:
        return 0.0
    if t >= 1.0:
        return 1.0
    f = t - 1.0
    return f * f * ((s + 1.0) * f + s) + 1.0


def lerp(a: float, b: float, t: float) -> float:
    """Linear interpolation. t in [0, 1]."""
    return a + (b - a) * t


def lerp_color(c1: str, c2: str, t: float) -> str:
    """Linear interpolation between two ``#rrggbb`` colors. t in [0, 1]."""
    a = _parse_hex(c1)
    b = _parse_hex(c2)
    return "#{:02X}{:02X}{:02X}".format(
        int(lerp(a[0], b[0], t)),
        int(lerp(a[1], b[1], t)),
        int(lerp(a[2], b[2], t)),
    )


def _parse_hex(c: str) -> tuple[int, int, int]:
    c = c.lstrip("#")
    if len(c) == 3:
        c = "".join(ch * 2 for ch in c)
    return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)


def with_alpha(hex_color: str, alpha_hex: str) -> str:
    """Append an alpha byte to a ``#rrggbb`` color → ``#rrggbbaa``."""
    if not hex_color.startswith("#"):
        return hex_color
    if len(hex_color) == 9:
        return hex_color
    return hex_color + alpha_hex


# ---------------------------------------------------------------------------
# Diagnostics
# ---------------------------------------------------------------------------


def describe() -> dict[str, Any]:
    """Return a snapshot of the active tokens. Useful for the about dialog
    and for debugging."""
    return {
        "colors": {
            "bg.canvas": COLORS.bg.canvas,
            "bg.panel": COLORS.bg.panel,
            "bg.elevated": COLORS.bg.elevated,
            "bg.hover": COLORS.bg.hover,
            "bg.selected": COLORS.bg.selected,
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
        "motion": {
            "fast_ms": MOTION.fast,
            "default_ms": MOTION.DEFAULT,
            "slow_ms": MOTION.slow,
            "reduced_motion": MOTION.reduced_motion,
        },
    }
