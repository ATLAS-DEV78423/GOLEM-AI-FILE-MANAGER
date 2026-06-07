"""Reusable, themed components for the GOLEM UI.

Every component reads colors, spacing, radii, typography, and motion
from :mod:`golem.ui_theme`. None of them paint hex literals directly.

Component catalog
-----------------
- :class:`PathField`      — label + entry + browse button (for folder
  pickers in onboarding).
- :class:`SecretField`    — label + masked entry + show/hide + async
  test button with spinner.
- :class:`PrimaryButton`   — copper gradient button with press feedback.
- :class:`SecondaryButton` — ghost-style button for cancel/back.
- :class:`IconButton`      — small square button with a single icon.
- :class:`StatusPill`      — small colored pill (success/warn/error/info).
- :class:`CategoryBadge`   — small color-coded category indicator.
- :class:`EmptyState`      — icon + headline + body + optional action.
- :class:`KeyboardHint`    — small monospace key cap chip.
- :class:`Separator`       — hairline divider.
- :class:`StepIndicator`   — 4-step progress dots for onboarding.
- :class:`HoverList`       — virtualized Canvas list with hover rings
  and selection (used by the search popup).
- :class:`IndeterminateBar`— thin colored progress bar.
"""

from __future__ import annotations

import logging
import tkinter as tk
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from tkinter import filedialog, ttk
from typing import Any, Literal, cast

from .ui_anim import (
    _Animation,
    color_transition,
    shimmer_skeleton,
)
from .ui_icons import get_icon
from .ui_theme import (
    COLORS,
    ICON_SIZE,
    SIZE,
    SPACING,
    TYPOGRAPHY,
)

_LOG = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Frame helpers
# ---------------------------------------------------------------------------


def make_panel(
    parent: tk.Misc,
    *,
    bg: str | None = None,
    padx: int = 0,
    pady: int = 0,
) -> ttk.Frame:
    """A bordered panel frame (one subtle hairline)."""
    bg = bg or COLORS.bg.panel
    outer = tk.Frame(parent, bg=COLORS.border.subtle, bd=0, highlightthickness=0)
    inner = tk.Frame(outer, bg=bg, bd=0, highlightthickness=0)
    inner.pack(fill="both", expand=True, padx=1, pady=1)
    inner._golem_outer = outer  # type: ignore[attr-defined]
    if padx or pady:
        inner.pack_propagate(False)
    return inner  # type: ignore[return-value]


def add_hover(
    widget: tk.Misc,
    on_enter: Callable[[], None],
    on_leave: Callable[[], None],
) -> None:
    """Bind mouse enter/leave to a widget. Recurses into the canvas and
    ttk frames transparently."""
    widget.bind("<Enter>", lambda _e: on_enter())
    widget.bind("<Leave>", lambda _e: on_leave())
    for child in widget.winfo_children():
        try:
            add_hover(child, on_enter, on_leave)
        except tk.TclError:
            pass


# ---------------------------------------------------------------------------
# PathField
# ---------------------------------------------------------------------------


@dataclass
class PathField:
    """A label + entry + browse button for a folder path."""

    parent: tk.Misc
    label: str
    variable: tk.StringVar
    on_browse: Callable[[], None] | None = None
    placeholder: str = ""

    _root: tk.Frame = field(init=False, repr=False)
    _entry: ttk.Entry = field(init=False, repr=False)
    _button: ttk.Button = field(init=False, repr=False)
    _placeholder_active: bool = field(init=False, default=False, repr=False)

    def build(self) -> tk.Frame:
        self._root = tk.Frame(self.parent, bg=COLORS.bg.panel)
        lbl = ttk.Label(self._root, text=self.label, style="Caption.TLabel")
        lbl.pack(anchor="w", pady=(0, SPACING.xs))

        row = tk.Frame(self._root, bg=COLORS.bg.panel)
        row.pack(fill="x")
        self._entry = ttk.Entry(row, textvariable=self.variable)
        self._entry.pack(side="left", fill="x", expand=True)
        # Focus ring animation for accessibility
        try:

            def _pf_focus_in(_e: tk.Event) -> None:
                self._entry._golem_focus_anim = color_transition(  # type: ignore[attr-defined]
                    self._entry,
                    attribute="bordercolor",
                    from_color=COLORS.border.DEFAULT,
                    to_color=COLORS.accent.ring,
                    duration_ms=160,
                )

            def _pf_focus_out(_e: tk.Event) -> None:
                a = getattr(self._entry, "_golem_focus_anim", None)
                if isinstance(a, _Animation):
                    a.cancel()
                try:
                    cast(Any, self._entry).configure(bordercolor=COLORS.border.DEFAULT)
                except tk.TclError:
                    pass

            self._entry.bind("<FocusIn>", _pf_focus_in)
            self._entry.bind("<FocusOut>", _pf_focus_out)
        except tk.TclError:
            pass
        self._button = ttk.Button(
            row,
            text="Browse",
            style="Ghost.TButton",
            command=self._browse,
        )
        self._button.pack(side="left", padx=(SPACING.sm, 0))
        return self._root

    def _browse(self) -> None:
        if self.on_browse is not None:
            self.on_browse()
            return
        folder = filedialog.askdirectory(parent=self._root.winfo_toplevel())
        if folder:
            self.variable.set(folder)

    def focus(self) -> None:
        self._entry.focus_set()


# ---------------------------------------------------------------------------
# SecretField — API key entry with show/hide + async test
# ---------------------------------------------------------------------------


@dataclass
class SecretField:
    """Label + entry (masked) + show/hide + test button + result line."""

    parent: tk.Misc
    label: str
    variable: tk.StringVar
    on_test: Callable[[], tuple[bool, str]] | None = None
    test_async: Callable[[], None] | None = None

    _root: tk.Frame = field(init=False, repr=False)
    _entry: ttk.Entry = field(init=False, repr=False)
    _test_btn: ttk.Button = field(init=False, repr=False)
    _toggle_btn: ttk.Button = field(init=False, repr=False)
    _result_var: tk.StringVar = field(init=False, repr=False)
    _result_label: ttk.Label = field(init=False, repr=False)
    _showing: bool = field(init=False, default=False, repr=False)

    def build(self) -> tk.Frame:
        self._root = tk.Frame(self.parent, bg=COLORS.bg.panel)
        ttk.Label(self._root, text=self.label, style="Caption.TLabel").pack(
            anchor="w", pady=(0, SPACING.xs)
        )
        row = tk.Frame(self._root, bg=COLORS.bg.panel)
        row.pack(fill="x")
        self._entry = ttk.Entry(row, textvariable=self.variable, show="•")
        self._entry.pack(side="left", fill="x", expand=True)

        try:

            def _sf_focus_in(_e: tk.Event) -> None:
                self._entry._golem_focus_anim = color_transition(  # type: ignore[attr-defined]
                    self._entry,
                    attribute="bordercolor",
                    from_color=COLORS.border.DEFAULT,
                    to_color=COLORS.accent.ring,
                    duration_ms=160,
                )

            def _sf_focus_out(_e: tk.Event) -> None:
                a = getattr(self._entry, "_golem_focus_anim", None)
                if isinstance(a, _Animation):
                    a.cancel()
                try:
                    cast(Any, self._entry).configure(bordercolor=COLORS.border.DEFAULT)
                except tk.TclError:
                    pass

            self._entry.bind("<FocusIn>", _sf_focus_in)
            self._entry.bind("<FocusOut>", _sf_focus_out)
        except tk.TclError:
            pass

        self._toggle_btn = ttk.Button(
            row,
            text="Show",
            style="Ghost.TButton",
            command=self._toggle,
            width=6,
        )
        self._toggle_btn.pack(side="left", padx=(SPACING.xs, 0))

        self._test_btn = ttk.Button(
            row,
            text="Test",
            style="Primary.TButton",
            command=self._on_test_clicked,
            width=8,
        )
        self._test_btn.pack(side="left", padx=(SPACING.xs, 0))

        self._result_var = tk.StringVar(value="")
        self._result_label = ttk.Label(
            self._root, textvariable=self._result_var, style="Caption.TLabel"
        )
        self._result_label.pack(anchor="w", pady=(SPACING.xs, 0))
        return self._root

    def _toggle(self) -> None:
        self._showing = not self._showing
        self._entry.configure(show="" if self._showing else "•")
        self._toggle_btn.configure(text="Hide" if self._showing else "Show")

    def _on_test_clicked(self) -> None:
        if self.test_async is not None:
            self.test_async()
            return
        if self.on_test is None:
            return
        self._result_var.set("Testing...")
        self._result_label.configure(foreground=COLORS.fg.tertiary)
        self._test_btn.state(["disabled"])

        def _run():
            try:
                ok, msg = self.on_test()
            except Exception as exc:
                ok, msg = False, str(exc)
            self._test_btn.state(["!disabled"])
            self.set_result(ok, msg)

        self._root.after(50, _run)

    def set_result(self, ok: bool, message: str) -> None:
        prefix = "✓ " if ok else "✗ "
        self._result_var.set(f"{prefix}{message}")
        self._result_label.configure(foreground=COLORS.state.success if ok else COLORS.state.error)

    def set_testing(self, message: str = "Testing") -> None:
        self._result_var.set(message)
        self._result_label.configure(foreground=COLORS.fg.tertiary)
        self._test_btn.state(["disabled"])

    def clear_testing(self) -> None:
        self._test_btn.state(["!disabled"])
        self._result_var.set("")
        self._result_label.configure(foreground=COLORS.fg.tertiary)

    def focus(self) -> None:
        self._entry.focus_set()


# ---------------------------------------------------------------------------
# Buttons
# ---------------------------------------------------------------------------


def PrimaryButton(
    parent: tk.Misc,
    text: str,
    command: Callable[[], None],
    *,
    width: int | str | None = None,
) -> ttk.Button:
    w: int | str
    if width is None:
        w = ""
    elif isinstance(width, str):
        w = int(width) if width.isdigit() else ""
    else:
        w = width
    call_w: int | Literal[""] = w if isinstance(w, int) else ""
    btn = ttk.Button(parent, text=text, style="Primary.TButton", command=command, width=call_w)

    def _cancel_anim(b: ttk.Button) -> None:
        a = getattr(b, "_golem_anim", None)
        if isinstance(a, _Animation):
            a.cancel()

    def _on_enter(_e: tk.Event) -> None:
        _cancel_anim(btn)
        btn._golem_anim = color_transition(  # type: ignore[attr-defined]
            btn,
            attribute="background",
            from_color=COLORS.accent.DEFAULT,
            to_color=COLORS.accent.hover,
            duration_ms=120,
        )

    def _on_leave(_e: tk.Event) -> None:
        _cancel_anim(btn)
        btn._golem_anim = color_transition(  # type: ignore[attr-defined]
            btn,
            attribute="background",
            from_color=COLORS.accent.hover,
            to_color=COLORS.accent.DEFAULT,
            duration_ms=120,
        )

    def _on_press(_e: tk.Event) -> None:
        _cancel_anim(btn)
        btn._golem_anim = color_transition(  # type: ignore[attr-defined]
            btn,
            attribute="background",
            from_color=COLORS.accent.hover,
            to_color=COLORS.accent.pressed,
            duration_ms=60,
        )

    def _on_release(_e: tk.Event) -> None:
        _cancel_anim(btn)
        btn._golem_anim = color_transition(  # type: ignore[attr-defined]
            btn,
            attribute="background",
            from_color=COLORS.accent.pressed,
            to_color=COLORS.accent.hover,
            duration_ms=120,
        )

    def _on_focus_in(_e: tk.Event) -> None:
        _cancel_anim(btn)
        btn._golem_focus_anim = color_transition(  # type: ignore[attr-defined]
            btn,
            attribute="bordercolor",
            from_color=COLORS.accent.DEFAULT,
            to_color=COLORS.accent.ring,
            duration_ms=160,
        )

    def _on_focus_out(_e: tk.Event) -> None:
        a = getattr(btn, "_golem_focus_anim", None)
        if isinstance(a, _Animation):
            a.cancel()
        try:
            cast(Any, btn).configure(bordercolor=COLORS.accent.DEFAULT)
        except tk.TclError:
            pass

    try:
        btn.bind("<Enter>", _on_enter)
        btn.bind("<Leave>", _on_leave)
        btn.bind("<ButtonPress-1>", _on_press)
        btn.bind("<ButtonRelease-1>", _on_release)
        btn.bind("<FocusIn>", _on_focus_in)
        btn.bind("<FocusOut>", _on_focus_out)
    except tk.TclError:
        pass

    return btn



def SecondaryButton(
    parent: tk.Misc,
    text: str,
    command: Callable[[], None],
    *,
    width: int | str | None = None,
) -> ttk.Button:
    w: int | str
    if width is None:
        w = ""
    elif isinstance(width, str):
        w = int(width) if width.isdigit() else ""
    else:
        w = width
    call_w: int | Literal[""] = w if isinstance(w, int) else ""
    btn = ttk.Button(parent, text=text, style="Ghost.TButton", command=command, width=call_w)

    def _cancel_anim(b: ttk.Button) -> None:
        a = getattr(b, "_golem_anim", None)
        if isinstance(a, _Animation):
            a.cancel()

    def _on_enter(_e: tk.Event) -> None:
        _cancel_anim(btn)
        btn._golem_anim = color_transition(  # type: ignore[attr-defined]
            btn,
            attribute="background",
            from_color=COLORS.bg.panel,
            to_color=COLORS.bg.hover,
            duration_ms=120,
        )

    def _on_leave(_e: tk.Event) -> None:
        _cancel_anim(btn)
        btn._golem_anim = color_transition(  # type: ignore[attr-defined]
            btn,
            attribute="background",
            from_color=COLORS.bg.hover,
            to_color=COLORS.bg.panel,
            duration_ms=120,
        )

    def _on_focus_in(_e: tk.Event) -> None:
        _cancel_anim(btn)
        btn._golem_focus_anim = color_transition(  # type: ignore[attr-defined]
            btn,
            attribute="bordercolor",
            from_color=COLORS.border.subtle,
            to_color=COLORS.accent.ring,
            duration_ms=160,
        )

    def _on_focus_out(_e: tk.Event) -> None:
        a = getattr(btn, "_golem_focus_anim", None)
        if isinstance(a, _Animation):
            a.cancel()
        try:
            cast(Any, btn).configure(bordercolor=COLORS.border.subtle)
        except tk.TclError:
            pass

    try:
        btn.bind("<Enter>", _on_enter)
        btn.bind("<Leave>", _on_leave)
        btn.bind("<FocusIn>", _on_focus_in)
        btn.bind("<FocusOut>", _on_focus_out)
    except tk.TclError:
        pass

    return btn


@dataclass
class IconButton:
    """A small square button with a single icon and an optional label."""

    parent: tk.Misc
    icon: str
    command: Callable[[], None]
    label: str = ""
    tooltip: str = ""
    color: str = COLORS.fg.secondary
    active_color: str = COLORS.fg.primary
    size: int = 32

    _btn: tk.Button = field(init=False, repr=False)
    _img_normal: tk.PhotoImage = field(init=False, repr=False)
    _img_hover: tk.PhotoImage = field(init=False, repr=False)
    _hovered: bool = field(init=False, default=False, repr=False)
    _label: ttk.Label = field(init=False, repr=False)

    def build(self) -> tk.Frame:
        # We use a plain tk.Button (not ttk) because tk supports
        # ``image`` + ``compound`` and gives us full control over
        # hover/leave colour transitions.
        icon_size = max(ICON_SIZE.sm, self.size - 14)
        self._img_normal = get_icon(self.icon, size=icon_size, color=self.color, master=self.parent)
        self._img_hover = get_icon(
            self.icon, size=icon_size, color=self.active_color, master=self.parent
        )
        frame = tk.Frame(self.parent, bg=COLORS.bg.panel)
        self._btn = tk.Button(
            frame,
            image=self._img_normal,
            bg=COLORS.bg.panel,
            activebackground=COLORS.bg.hover,
            bd=0,
            highlightthickness=0,
            relief="flat",
            cursor="hand2",
            width=self.size,
            height=self.size,
            command=self.command,
        )
        self._btn.pack(side="left")
        self._btn.bind("<Enter>", lambda _e: self._set_hovered(True))
        self._btn.bind("<Leave>", lambda _e: self._set_hovered(False))
        if self.label:
            self._label = ttk.Label(frame, text=self.label, style="Caption.TLabel")
            self._label.pack(side="left", padx=(SPACING.xs, 0))
            self._label.bind("<Enter>", lambda _e: self._set_hovered(True))
            self._label.bind("<Leave>", lambda _e: self._set_hovered(False))
        if self.tooltip:
            self._install_tooltip(self.tooltip)
        return frame

    def _set_hovered(self, hovered: bool) -> None:
        if hovered == self._hovered:
            return
        self._hovered = hovered
        try:
            self._btn.configure(
                image=self._img_hover if hovered else self._img_normal,
                bg=COLORS.bg.hover if hovered else COLORS.bg.panel,
            )
        except tk.TclError:
            pass

    def _install_tooltip(self, text: str) -> None:
        tip: dict[str, Any] = {"win": None}

        def show(_e=None):
            try:
                if tip["win"] is not None and tip["win"].winfo_exists():
                    return
                x = self._btn.winfo_rootx() + self._btn.winfo_width() // 2
                y = self._btn.winfo_rooty() + self._btn.winfo_height() + 6
                win = tk.Toplevel(self._btn)
                win.wm_overrideredirect(True)
                win.geometry(f"+{x}+{y}")
                ttk.Label(win, text=text, style="Kbd.TLabel", padding=(8, 4)).pack()
                tip["win"] = win
            except tk.TclError:
                pass

        def hide(_e=None):
            try:
                if tip["win"] is not None:
                    tip["win"].destroy()
                tip["win"] = None
            except tk.TclError:
                pass

        def _on_enter(e=None):
            self._set_hovered(True)
            show(e)
            return None

        def _on_leave(e=None):
            self._set_hovered(False)
            hide(e)
            return None

        for w in (self._btn, getattr(self, "_label", self._btn)):
            w.bind("<Enter>", _on_enter, add="+")
            w.bind("<Leave>", _on_leave, add="+")


# ---------------------------------------------------------------------------
# StatusPill / CategoryBadge
# ---------------------------------------------------------------------------


def StatusPill(
    parent: tk.Misc,
    text: str,
    *,
    state: str = "neutral",  # one of: neutral, success, warning, error, info
) -> tk.Frame:
    """A small rounded pill with text. Pure tk.Canvas for the rounded
    background so the corners actually look like a pill."""
    colors = {
        "neutral": (COLORS.bg.elevated, COLORS.fg.secondary),
        "success": (COLORS.state.success_muted, COLORS.state.success),
        "warning": (COLORS.state.warning_muted, COLORS.state.warning),
        "error": (COLORS.state.error_muted, COLORS.state.error),
        "info": (COLORS.state.info_muted, COLORS.state.info),
    }
    bg, fg = colors.get(state, colors["neutral"])
    frame = tk.Frame(parent, bg=bg, bd=0, highlightthickness=0)
    padx, pady = 8, 3
    lbl = tk.Label(
        frame,
        text=text,
        bg=bg,
        fg=fg,
        font=TYPOGRAPHY.micro.font(),
        padx=padx,
        pady=pady,
    )
    lbl.pack()
    return frame


def CategoryBadge(parent: tk.Misc, category: str) -> tk.Label:
    """Small colored indicator for a search result's category."""
    key = (category or "other").lower()
    color = getattr(COLORS.category, key, COLORS.category.other)
    dot = "●"
    return tk.Label(
        parent,
        text=f"{dot}  {category}",
        bg=COLORS.bg.panel,
        fg=color,
        font=TYPOGRAPHY.caption.font(),
        padx=0,
        pady=0,
    )


# ---------------------------------------------------------------------------
# EmptyState
# ---------------------------------------------------------------------------


@dataclass
class EmptyState:
    """Icon + headline + body + optional action button. Centered."""

    parent: tk.Misc
    icon: str
    headline: str
    body: str = ""
    action_label: str = ""
    on_action: Callable[[], None] | None = None

    _frame: tk.Frame = field(init=False, repr=False)

    def build(self) -> tk.Frame:
        self._frame = tk.Frame(self.parent, bg=COLORS.bg.panel)
        inner = tk.Frame(self._frame, bg=COLORS.bg.panel)
        inner.place(relx=0.5, rely=0.42, anchor="center")

        # Icon with subtle glow ring
        glow_frame = tk.Frame(inner, bg=COLORS.bg.elevated, bd=0, highlightthickness=0)
        icon_size = 56
        icon_canvas = tk.Canvas(
            glow_frame,
            width=icon_size,
            height=icon_size,
            bg=COLORS.bg.elevated,
            highlightthickness=0,
            bd=0,
        )
        icon_canvas.pack()
        # Draw rounded background
        r = icon_size // 2
        icon_canvas.create_arc(
            0,
            0,
            icon_size,
            icon_size,
            start=0,
            extent=360,
            fill=COLORS.bg.panel,
            outline=COLORS.border.subtle,
        )
        icon_img = get_icon(self.icon, size=24, color=COLORS.fg.secondary, master=icon_canvas)
        icon_canvas.create_image(icon_size // 2, icon_size // 2, image=icon_img)
        icon_canvas.image = icon_img  # type: ignore[attr-defined]
        glow_frame.pack(pady=(0, SPACING.lg))

        head_lbl = ttk.Label(inner, text=self.headline, style="Title.TLabel")
        head_lbl.pack(pady=(0, SPACING.xs))
        if self.body:
            body_lbl = ttk.Label(
                inner, text=self.body, style="Caption.TLabel", wraplength=380, justify="center"
            )
            body_lbl.pack(pady=(0, SPACING.lg))
        # Subtle loading pulse when used as a spinner placeholder
        if self.icon == "spinner":
            try:
                from .ui_anim import pulse

                anim = pulse(
                    head_lbl,
                    attribute="foreground",
                    low=COLORS.fg.tertiary,
                    high=COLORS.accent.DEFAULT,
                    period_ms=900,
                )
                # store to allow garbage collection / cancellation if needed
                self._frame._golem_anim = anim  # type: ignore[attr-defined]
            except Exception:
                pass
        if self.action_label and self.on_action is not None:
            PrimaryButton(inner, text=self.action_label, command=self.on_action).pack()
        return self._frame


# ---------------------------------------------------------------------------
# File type emoji icons
# ---------------------------------------------------------------------------


_FILE_TYPE_EMOJI: dict[str, str] = {
    "pdf": "\U0001f4c4",
    "docx": "\U0001f4dd",
    "doc": "\U0001f4dd",
    "xlsx": "\U0001f4ca",
    "xls": "\U0001f4ca",
    "csv": "\U0001f4ca",
    "md": "\U0001f4cb",
    "markdown": "\U0001f4cb",
    "txt": "\U0001f4cb",
    "png": "\U0001f5bc\ufe0f",
    "jpg": "\U0001f5bc\ufe0f",
    "jpeg": "\U0001f5bc\ufe0f",
    "gif": "\U0001f5bc\ufe0f",
    "svg": "\U0001f5bc\ufe0f",
    "webp": "\U0001f5bc\ufe0f",
    "mp4": "\U0001f3ac",
    "mov": "\U0001f3ac",
    "avi": "\U0001f3ac",
    "mkv": "\U0001f3ac",
    "webm": "\U0001f3ac",
    "mp3": "\U0001f399\ufe0f",
    "wav": "\U0001f399\ufe0f",
    "flac": "\U0001f399\ufe0f",
    "m4a": "\U0001f399\ufe0f",
    "folder": "\U0001f4c1",
    "py": "\U0001f4bb",
    "js": "\U0001f4bb",
    "ts": "\U0001f4bb",
    "jsx": "\U0001f4bb",
    "tsx": "\U0001f4bb",
    "html": "\U0001f4bb",
    "css": "\U0001f4bb",
    "json": "\U0001f4bb",
    "yaml": "\U0001f4bb",
    "yml": "\U0001f4bb",
    "zip": "\U0001f4e6",
    "rar": "\U0001f4e6",
    "tar": "\U0001f4e6",
    "gz": "\U0001f4e6",
    "ppt": "\U0001f4f1",  # using presentation emoji
    "pptx": "\U0001f4f1",
}


def file_type_emoji(file_type: str) -> str:
    """Return the emoji icon for a given file type extension."""
    return _FILE_TYPE_EMOJI.get(file_type.lower().strip("."), "\U0001f4ce")


def file_type_from_name(filename: str) -> str:
    """Guess the file type from a filename."""
    if not filename:
        return "unknown"
    _, ext = filename.rsplit(".", 1) if "." in filename else (filename, "")
    # Map extensions to semantic types
    type_map: dict[str, str] = {
        "pdf": "pdf",
        "doc": "docx",
        "docx": "docx",
        "xls": "xlsx",
        "xlsx": "xlsx",
        "csv": "csv",
        "md": "md",
        "txt": "txt",
        "png": "image",
        "jpg": "image",
        "jpeg": "image",
        "gif": "image",
        "svg": "image",
        "webp": "image",
        "mp4": "video",
        "mov": "video",
        "avi": "video",
        "mkv": "video",
        "webm": "video",
        "mp3": "audio",
        "wav": "audio",
        "flac": "audio",
        "m4a": "audio",
        "py": "code",
        "js": "code",
        "ts": "code",
        "jsx": "code",
        "tsx": "code",
        "html": "code",
        "css": "code",
        "json": "code",
        "yaml": "code",
        "yml": "code",
        "zip": "archive",
        "rar": "archive",
        "tar": "archive",
        "gz": "archive",
        "ppt": "presentation",
        "pptx": "presentation",
    }
    return type_map.get(ext.lower(), "unknown")


# ---------------------------------------------------------------------------
# SectionLabel — grouped result header (per spec)
# ---------------------------------------------------------------------------


def SectionLabel(parent: tk.Misc, text: str) -> ttk.Label:
    """An orange, uppercase, monospace section label for grouped results."""
    lbl = ttk.Label(
        parent,
        text=text,
        style="Caption.TLabel",
        font=TYPOGRAPHY.caption.font(),
        foreground=COLORS.accent.DEFAULT,
    )
    return lbl


# ---------------------------------------------------------------------------
# KeyboardHint
# ---------------------------------------------------------------------------


def KeyboardHint(parent: tk.Misc, key: str, *, style: str = "Kbd.TLabel") -> ttk.Label:
    """A small monospace chip representing a keyboard shortcut."""
    return ttk.Label(parent, text=f"  {key}  ", style=style)


# ---------------------------------------------------------------------------
# Separator
# ---------------------------------------------------------------------------


def Separator(parent: tk.Misc, *, horizontal: bool = True) -> tk.Frame:
    """A 1-px hairline divider in ``border.subtle``."""
    if horizontal:
        return tk.Frame(parent, bg=COLORS.border.subtle, height=1, bd=0, highlightthickness=0)
    return tk.Frame(parent, bg=COLORS.border.subtle, width=1, bd=0, highlightthickness=0)


# ---------------------------------------------------------------------------
# Step indicator — 4 dots, current step accented
# ---------------------------------------------------------------------------


@dataclass
class StepIndicator:
    parent: tk.Misc
    steps: list[str]
    current: int = 0

    _frame: tk.Frame = field(init=False, repr=False)
    _dots: list[tk.Canvas] = field(init=False, default_factory=list, repr=False)
    _labels: list[ttk.Label | None] = field(init=False, default_factory=list, repr=False)
    _connectors: list[tk.Frame] = field(init=False, default_factory=list, repr=False)

    def build(self) -> tk.Frame:
        self._frame = tk.Frame(self.parent, bg=COLORS.bg.panel)
        for idx, name in enumerate(self.steps):
            col = tk.Frame(self._frame, bg=COLORS.bg.panel)
            col.pack(side="left", expand=True, fill="x")
            dot = tk.Canvas(
                col, width=12, height=12, bg=COLORS.bg.panel, highlightthickness=0, bd=0
            )
            dot.pack(side="left", padx=(SPACING.md, SPACING.xs))
            self._dots.append(dot)
            lbl = ttk.Label(col, text=name, style="Micro.TLabel")
            lbl.pack(side="left")
            self._labels.append(lbl)
            if idx < len(self.steps) - 1:
                sep = tk.Frame(self._frame, bg=COLORS.border.subtle, height=1, bd=0)
                sep.pack(side="left", fill="x", expand=True, padx=SPACING.sm)
                self._connectors.append(sep)
        self._render()
        return self._frame

    def set_current(self, idx: int) -> None:
        self.current = max(0, min(idx, len(self.steps) - 1))
        self._render()

    def _render(self) -> None:
        for i, dot in enumerate(self._dots):
            dot.delete("all")
            if i < self.current:
                color = COLORS.accent.DEFAULT
                dot.create_oval(2, 2, 10, 10, fill=color, outline=color)
            elif i == self.current:
                # Copper ring with dark fill
                dot.create_oval(
                    2, 2, 10, 10, fill=COLORS.bg.panel, outline=COLORS.accent.DEFAULT, width=2
                )
            else:
                dot.create_oval(
                    2, 2, 10, 10, fill=COLORS.bg.elevated, outline=COLORS.border.DEFAULT
                )


# ---------------------------------------------------------------------------
# HoverList — virtualized Canvas list with hover + selection
# ---------------------------------------------------------------------------


@dataclass
class _RowSpec:
    """One rendered row. Subclasses build these from their data."""

    primary: str
    secondary: str = ""
    tertiary: str = ""
    badge: tuple[str, str] | None = None  # (text, color)
    match_pill: tuple[str, str] | None = None  # (match_type, color) — why-matched indicator
    related_badges: list[tuple[str, str]] = field(default_factory=list)  # related file/tag badges
    payload: Any = None


@dataclass
class HoverList:
    """A virtualized canvas-based list with hover rings and selection.

    Designed for the search popup: fast scroll, keyboard nav, hover
    feedback, click + double-click handlers.
    """

    parent: tk.Misc
    on_activate: Callable[[Any], None]
    on_reveal: Callable[[Any], None] | None = None
    row_height: int = SIZE.row_height

    _canvas: tk.Canvas = field(init=False, repr=False)
    _scrollbar: ttk.Scrollbar = field(init=False, repr=False)
    _frame: tk.Frame = field(init=False, repr=False)
    _rows: list[_RowSpec] = field(init=False, default_factory=list, repr=False)
    _selected: int = field(init=False, default=-1, repr=False)
    _hovered: int = field(init=False, default=-1, repr=False)
    _offset: int = field(init=False, default=0, repr=False)
    _visible_count: int = field(init=False, default=0, repr=False)
    _items_per_page: int = field(init=False, default=20, repr=False)
    _total_height: int = field(init=False, default=0, repr=False)
    _last_motion_y: int = field(init=False, default=0, repr=False)
    _empty_widgets: tuple | None = field(init=False, default=None, repr=False)

    def build(self) -> tk.Frame:
        self._frame = tk.Frame(self.parent, bg=COLORS.bg.panel)
        self._canvas = tk.Canvas(
            self._frame,
            bg=COLORS.bg.panel,
            bd=0,
            highlightthickness=0,
            takefocus=1,
        )
        self._scrollbar = ttk.Scrollbar(
            self._frame,
            orient="vertical",
            command=self._on_scrollbar,
            style="Vertical.TScrollbar",
        )
        self._canvas.configure(yscrollcommand=self._scrollbar.set)
        self._canvas.pack(side="left", fill="both", expand=True)
        self._scrollbar.pack(side="right", fill="y")

        self._canvas.bind("<Configure>", lambda _e: self._render())
        self._canvas.bind("<Motion>", self._on_motion)
        self._canvas.bind("<Leave>", lambda _e: self._set_hovered(-1))
        self._canvas.bind("<Button-1>", self._on_click)
        self._canvas.bind("<Double-Button-1>", self._on_double_click)
        self._canvas.bind("<Button-3>", self._on_right_click)
        self._canvas.bind("<MouseWheel>", self._on_mousewheel)
        return self._frame

    def set_rows(self, rows: Sequence[_RowSpec] | list[dict[str, Any]]) -> None:
        """Replace the list contents. Accepts either ``_RowSpec`` objects
        or plain dicts with the same keys."""
        normalized: list[_RowSpec] = []
        for r in rows:
            if isinstance(r, _RowSpec):
                normalized.append(r)
            else:
                normalized.append(
                    _RowSpec(
                        primary=str(r.get("primary", "")),
                        secondary=str(r.get("secondary", "")),
                        tertiary=str(r.get("tertiary", "")),
                        badge=r.get("badge"),
                        related_badges=r.get("related_badges", []),
                        payload=r.get("payload"),
                    )
                )
        self._rows = normalized
        if self._selected >= len(self._rows):
            self._selected = len(self._rows) - 1
        self._offset = 0
        self._render()

    def select_next(self) -> None:
        if not self._rows:
            return
        self._select(min(self._selected + 1, len(self._rows) - 1))

    def select_prev(self) -> None:
        if not self._rows:
            return
        self._select(max(self._selected - 1, 0))

    def select_first(self) -> None:
        if self._rows:
            self._select(0)

    def select_last(self) -> None:
        if self._rows:
            self._select(len(self._rows) - 1)

    def get_selected_payload(self) -> Any:
        if 0 <= self._selected < len(self._rows):
            return self._rows[self._selected].payload
        return None

    def show_shimmer(self) -> None:
        """Display a shimmer skeleton loading state in the list area.

        Replaces the previous empty state with a subtle sweep animation
        that looks like rows being loaded.
        """
        self._clear_items()
        self._rows = []
        self._selected = -1
        self._hovered = -1
        self._canvas.delete("all")
        # Draw 6 shimmer rows
        cw = max(100, self._canvas.winfo_width())
        ch = max(100, self._canvas.winfo_height())
        row_h = self.row_height
        num_rows = max(3, min(6, ch // row_h))
        start_y = (ch - num_rows * row_h) // 2
        # Cancel any previous shimmer
        if hasattr(self._canvas, "_golem_shimmer"):
            try:
                self._canvas._golem_shimmer.cancel()
            except Exception:
                pass
        for i in range(num_rows):
            y = start_y + i * row_h + 6
            bar_w = cw - 120 - int(40 * (i / num_rows))
            self._canvas.create_rectangle(
                20,
                y,
                20 + int(0.7 * bar_w),
                y + 14,
                fill=COLORS.bg.elevated,
                outline="",
                tags=("_shimmer_row",),
            )
            self._canvas.create_rectangle(
                20,
                y + 20,
                20 + int(0.4 * bar_w),
                y + 28,
                fill=COLORS.bg.elevated,
                outline="",
                tags=("_shimmer_row",),
            )
        try:
            anim = shimmer_skeleton(
                self._canvas,
                x=-20,
                y=-20,
                width=cw + 40,
                height=ch + 40,
                base_color=COLORS.bg.panel,
                highlight_color=COLORS.bg.elevated,
                period_ms=1600,
            )
            self._canvas._golem_shimmer = anim  # type: ignore[attr-defined]
        except Exception:
            pass

    def show_empty(self, icon: str, headline: str, body: str = "") -> None:
        """Display the empty state inside the list area."""
        self._clear_items()
        self._rows = []
        self._selected = -1
        self._hovered = -1
        self._canvas.delete("all")
        empty = EmptyState(self._canvas, icon=icon, headline=headline, body=body)
        empty.build()
        # Re-parent into the canvas, centered
        cw = max(1, self._canvas.winfo_width())
        ch = max(1, self._canvas.winfo_height())
        win = self._canvas.create_window(
            cw // 2,
            ch // 2,
            window=empty._frame,
        )
        self._empty_widgets = (empty, win)

    def _clear_items(self) -> None:
        if self._empty_widgets is not None:
            try:
                empty, win = self._empty_widgets
                self._canvas.delete(win)
                empty._frame.destroy()
            except tk.TclError:
                pass
            self._empty_widgets = None
        # Also cancel any in-flight shimmer
        if hasattr(self._canvas, "_golem_shimmer"):
            try:
                self._canvas._golem_shimmer.cancel()
            except Exception:
                pass
            self._canvas._golem_shimmer = None
        if self._empty_widgets is not None:
            try:
                empty, win = self._empty_widgets
                self._canvas.delete(win)
                empty._frame.destroy()
            except tk.TclError:
                pass
            self._empty_widgets = None

    def _select(self, idx: int) -> None:
        if idx == self._selected:
            return
        self._selected = idx
        # Make sure selected is visible with smooth scroll
        if idx < self._offset:
            self._offset = max(0, idx)
            self._sync_scrollbar()
        elif idx >= self._offset + self._items_per_page:
            self._offset = min(
                max(0, len(self._rows) - self._items_per_page),
                idx - self._items_per_page + 1,
            )
            self._sync_scrollbar()
        self._render()

    def _sync_scrollbar(self) -> None:
        """Update the scrollbar position to reflect the current offset."""
        total_rows = max(1, len(self._rows))
        max_offset = max(0, total_rows - self._items_per_page)
        if max_offset > 0:
            frac = self._offset / max_offset
            view = min(1.0, self._items_per_page / total_rows)
            self._scrollbar.set(frac, min(1.0, frac + view))
        else:
            self._scrollbar.set(0.0, 1.0)

    def _set_hovered(self, idx: int) -> None:
        if idx == self._hovered:
            return
        self._hovered = idx
        self._render()

    def _on_motion(self, event: tk.Event) -> None:
        y = event.y
        idx = (y // self.row_height) + self._offset
        if 0 <= idx < len(self._rows):
            self._set_hovered(idx)
        else:
            self._set_hovered(-1)

    def _on_click(self, event: tk.Event) -> None:
        y = event.y
        idx = (y // self.row_height) + self._offset
        if 0 <= idx < len(self._rows):
            self._select(idx)

    def _on_double_click(self, event: tk.Event) -> None:
        y = event.y
        idx = (y // self.row_height) + self._offset
        if 0 <= idx < len(self._rows):
            self._select(idx)
            payload = self._rows[idx].payload
            if payload is not None:
                self.on_activate(payload)

    def _on_right_click(self, event: tk.Event) -> None:
        y = event.y
        idx = (y // self.row_height) + self._offset
        if 0 <= idx < len(self._rows) and self.on_reveal is not None:
            self._select(idx)
            payload = self._rows[idx].payload
            if payload is not None:
                self.on_reveal(payload)

    def _on_mousewheel(self, event: tk.Event) -> None:
        delta = -1 if event.delta > 0 else 1
        self._scroll_by(delta * 3)

    def _on_scrollbar(self, *args: Any) -> None:
        if args[0] == "moveto":
            frac = float(args[1])
            max_offset = max(0, len(self._rows) - self._items_per_page)
            self._offset = int(round(frac * max_offset))
            self._render()
        elif args[0] == "scroll":
            amount = int(args[1])
            if "units" in args[2]:
                self._scroll_by(amount)
            else:
                self._scroll_by(amount * self._items_per_page)

    def _scroll_by(self, amount: int) -> None:
        max_offset = max(0, len(self._rows) - self._items_per_page)
        self._offset = max(0, min(self._offset + amount, max_offset))
        self._render()

    def _render(self) -> None:
        if not self._rows:
            return
        self._clear_items()
        self._canvas.delete("row")
        w = max(1, self._canvas.winfo_width())
        h = max(1, self._canvas.winfo_height())
        self._items_per_page = max(1, h // self.row_height)
        self._total_height = len(self._rows) * self.row_height

        for i in range(self._items_per_page + 1):
            idx = self._offset + i
            if idx >= len(self._rows):
                break
            y = i * self.row_height
            row = self._rows[idx]
            is_selected = idx == self._selected
            is_hovered = idx == self._hovered and not is_selected
            if is_selected:
                self._canvas.create_rectangle(
                    0,
                    y + 2,
                    w,
                    y + self.row_height - 2,
                    fill=COLORS.bg.selected,
                    outline="",
                )
                # Left accent bar
                self._canvas.create_rectangle(
                    0,
                    y + 6,
                    3,
                    y + self.row_height - 6,
                    fill=COLORS.accent.DEFAULT,
                    outline="",
                )
            elif is_hovered:
                self._canvas.create_rectangle(
                    0,
                    y + 2,
                    w,
                    y + self.row_height - 2,
                    fill=COLORS.bg.hover,
                    outline="",
                )

            # Primary
            self._canvas.create_text(
                SPACING.lg,
                y + self.row_height // 2 - 8,
                text=row.primary,
                fill=COLORS.fg.primary,
                font=TYPOGRAPHY.body_strong.font(),
                anchor="w",
            )
            # Secondary
            if row.secondary:
                self._canvas.create_text(
                    SPACING.lg,
                    y + self.row_height // 2 + 10,
                    text=row.secondary,
                    fill=COLORS.fg.secondary,
                    font=TYPOGRAPHY.caption.font(),
                    anchor="w",
                    width=w - SPACING.lg * 2,
                )
            # Match pill (why-matched — right-aligned)
            if row.match_pill:
                ptext, pcolor = row.match_pill
                pill_w = max(36, len(ptext) * 6 + 16)
                pill_h = 18
                px = w - SPACING.lg - pill_w
                py = y + self.row_height // 2 - pill_h // 2
                # Pill background with rounded look (simulated with rect)
                self._canvas.create_rectangle(
                    px,
                    py,
                    px + pill_w,
                    py + pill_h,
                    fill=COLORS.bg.panel,
                    outline=pcolor,
                    width=1,
                )
                self._canvas.create_text(
                    px + pill_w // 2,
                    py + pill_h // 2,
                    text=ptext,
                    fill=pcolor,
                    font=TYPOGRAPHY.pill.font(),
                    anchor="center",
                )
            # Badge (category) — left of match pill or right edge
            badge_right = (px - 8) if row.match_pill else (w - SPACING.lg)
            if row.badge:
                text, color = row.badge
                text_width = max(40, len(text) * 7 + 16)
                bx = badge_right - text_width
                by = y + self.row_height // 2
                self._canvas.create_rectangle(
                    bx,
                    by - 9,
                    bx + text_width,
                    by + 9,
                    fill=COLORS.bg.elevated,
                    outline=color,
                )
                self._canvas.create_text(
                    bx + text_width // 2,
                    by,
                    text=text,
                    fill=color,
                    font=TYPOGRAPHY.micro.font(),
                    anchor="center",
                )

            # Related file badges (bottom row)
            if row.related_badges:
                related_x = SPACING.lg
                related_y = y + self.row_height - 4
                max_related_w = w - SPACING.lg * 2
                for rtext, rcolor in row.related_badges:
                    rtw = max(20, len(rtext) * 6 + 12)
                    if related_x + rtw > max_related_w:
                        break
                    self._canvas.create_rectangle(
                        related_x,
                        related_y - 7,
                        related_x + rtw,
                        related_y + 7,
                        fill=COLORS.bg.panel,
                        outline=rcolor,
                    )
                    self._canvas.create_text(
                        related_x + rtw // 2,
                        related_y,
                        text=rtext,
                        fill=rcolor,
                        font=TYPOGRAPHY.kbd.font(),
                        anchor="center",
                    )
                    related_x += rtw + 4

        # Bottom fade — a thin gradient line at the very bottom edge
        self._canvas.create_rectangle(
            0,
            h - 8,
            w,
            h,
            fill=COLORS.bg.panel,
            outline="",
        )


# ---------------------------------------------------------------------------
# IndeterminateBar — a thin progress bar with moving fill
# ---------------------------------------------------------------------------


@dataclass
class SkeletonLoader:
    """A shimmer skeleton loader bar. No spinners — only skeleton shimmer."""

    parent: tk.Misc
    height: int = 3

    _canvas: tk.Canvas = field(init=False, repr=False)
    _anim: _Animation | None = field(init=False, default=None, repr=False)

    def build(self) -> tk.Canvas:
        self._canvas = tk.Canvas(
            self.parent,
            height=self.height,
            bg=COLORS.bg.panel,
            bd=0,
            highlightthickness=0,
        )
        return self._canvas

    def start(self) -> None:
        self.stop()
        self._anim = shimmer_skeleton(
            self._canvas,
            x=0,
            y=0,
            width=self._canvas.winfo_width() or 200,
            height=self.height,
            base_color=COLORS.bg.panel,
            highlight_color=COLORS.bg.elevated,
            period_ms=1600,
        )

    def stop(self) -> None:
        if self._anim is not None:
            self._anim.cancel()
            self._anim = None


# ---------------------------------------------------------------------------
# Footer hint row (used at the bottom of the search popup)
# ---------------------------------------------------------------------------


def FooterHints(
    parent: tk.Misc,
    hints: Sequence[tuple[str, str]],
) -> tk.Frame:
    """Render a row of ``<key> <action>`` hints.

    ``hints`` is a sequence of (key, action) tuples, e.g.
    ``[("↑↓", "navigate"), ("↵", "open"), ("⌘↵", "reveal"), ("esc", "close")]``.
    """
    frame = tk.Frame(parent, bg=COLORS.bg.titlebar, height=SIZE.statusbar_height)
    inner = tk.Frame(frame, bg=COLORS.bg.titlebar)
    inner.pack(side="left", padx=SPACING.lg, pady=SPACING.xs)
    for i, (key, action) in enumerate(hints):
        if i > 0:
            ttk.Label(inner, text="   ", style="Micro.TLabel").pack(side="left")
        KeyboardHint(inner, key).pack(side="left")
        ttk.Label(inner, text=f" {action} ", style="Micro.TLabel").pack(side="left")
    return frame


# ---------------------------------------------------------------------------
# Status bar (compact, used for errors and transient messages)
# ---------------------------------------------------------------------------


@dataclass
class StatusBar:
    """A one-line status bar at the bottom of a window.

    Three priority layers: errors take precedence over progress, which
    takes precedence over idle text. ``set_error`` displays an error
    icon + red text for ``duration_ms`` then falls back to whatever
    was last shown.
    """

    parent: tk.Misc
    _frame: tk.Frame = field(init=False, repr=False)
    _icon: tk.Label = field(init=False, repr=False)
    _dot: tk.Canvas = field(init=False, repr=False)
    _text_var: tk.StringVar = field(init=False, repr=False)
    _text: ttk.Label = field(init=False, repr=False)
    _anim: _Animation | None = field(init=False, default=None, repr=False)
    _error_after: str | None = field(init=False, default=None, repr=False)
    _last_idle: str = field(init=False, default="", repr=False)

    def build(self) -> tk.Frame:
        self._frame = tk.Frame(self.parent, bg=COLORS.bg.titlebar, height=SIZE.statusbar_height)
        inner = tk.Frame(self._frame, bg=COLORS.bg.titlebar)
        inner.pack(fill="x", padx=SPACING.lg, pady=SPACING.xs)
        # Status dot indicator (animated)
        self._dot = tk.Canvas(
            inner, width=6, height=6, bg=COLORS.bg.titlebar, highlightthickness=0, bd=0
        )
        self._dot.create_oval(0, 0, 6, 6, fill=COLORS.fg.tertiary, outline="", tags="dot")
        self._dot.pack(side="left", padx=(0, SPACING.sm))
        # Use a per-instance icon image so each window's StatusBar
        # doesn't share a PhotoImage across Tk interpreters.
        self._img_idle = get_icon("info", size=12, color=COLORS.fg.tertiary, master=inner)
        self._icon = tk.Label(
            inner,
            image=self._img_idle,
            bg=COLORS.bg.titlebar,
        )
        self._icon.image = self._img_idle  # type: ignore[attr-defined]
        self._icon.pack(side="left", padx=(0, SPACING.xs))
        self._text_var = tk.StringVar(value="")
        self._text = ttk.Label(inner, textvariable=self._text_var, style="Micro.TLabel")
        self._text.pack(side="left")
        return self._frame

    def set_idle(self, text: str) -> None:
        if self._error_after is not None:
            return
        self._last_idle = text
        self._text_var.set(text)
        self._text.configure(foreground=COLORS.fg.tertiary)
        self._set_dot(COLORS.fg.tertiary)
        self._set_icon("info", COLORS.fg.tertiary)

    def set_progress(self, text: str) -> None:
        if self._error_after is not None:
            return
        self._text_var.set(text)
        self._text.configure(foreground=COLORS.accent.DEFAULT)
        self._set_dot(COLORS.accent.DEFAULT)
        self._set_icon("spinner", COLORS.accent.DEFAULT)

    def set_error(self, text: str, duration_ms: int = 6000) -> None:
        self._text_var.set(text)
        self._text.configure(foreground=COLORS.state.error)
        self._set_dot(COLORS.state.error)
        self._set_icon("alert", COLORS.state.error)
        if self._error_after is not None:
            try:
                self._frame.after_cancel(self._error_after)
            except tk.TclError:
                pass
        self._error_after = self._frame.after(duration_ms, self._clear_error)

    def set_warning(self, text: str) -> None:
        self._text_var.set(text)
        self._text.configure(foreground=COLORS.state.warning)
        self._set_dot(COLORS.state.warning)
        self._set_icon("warning", COLORS.state.warning)

    def set_success(self, text: str) -> None:
        self._text_var.set(text)
        self._text.configure(foreground=COLORS.state.success)
        self._set_dot(COLORS.state.success)
        self._set_icon("check", COLORS.state.success)

    def _clear_error(self) -> None:
        self._error_after = None
        if self._last_idle:
            self.set_idle(self._last_idle)
        else:
            self._text_var.set("")
            self._text.configure(foreground=COLORS.fg.tertiary)
            self._set_dot(COLORS.fg.tertiary)
            self._set_icon("info", COLORS.fg.tertiary)

    def _set_dot(self, color: str) -> None:
        try:
            self._dot.delete("dot")
            self._dot.create_oval(0, 0, 6, 6, fill=color, outline="", tags="dot")
        except tk.TclError:
            pass

    def _set_icon(self, name: str, color: str) -> None:
        try:
            new = get_icon(name, size=12, color=color, master=self._icon)
            self._icon.configure(image=new)
            self._icon.image = new  # type: ignore[attr-defined]
        except tk.TclError:
            pass


class RoundedCard(tk.Canvas):
    """A beautiful card container with rounded corners and optional left vertical accent border."""

    def __init__(
        self,
        parent: tk.Misc,
        *,
        bg: str = COLORS.bg.panel,
        outline: str = COLORS.border.subtle,
        width: int = 1,
        radius: int = 12,
        left_accent: str | None = None,
        **kwargs,
    ):
        super().__init__(parent, bg=COLORS.bg.canvas, bd=0, highlightthickness=0, **kwargs)
        self.card_bg = bg
        self.card_outline = outline
        self.card_width = width
        self.card_radius = radius
        self.left_accent = left_accent

        # Frame inside the card
        self.inner_frame = tk.Frame(self, bg=bg, bd=0, highlightthickness=0)
        self._window_id = self.create_window(0, 0, window=self.inner_frame, anchor="nw")

        self.bind("<Configure>", self._on_configure)

    def _on_configure(self, event: tk.Event) -> None:
        self.redraw()

    def redraw(self) -> None:
        self.delete("card_bg")
        self.delete("card_border")

        w = self.winfo_width()
        h = self.winfo_height()
        r = self.card_radius
        bg = self.card_bg
        outline = self.card_outline
        wd = self.card_width

        if w <= 2 * r or h <= 2 * r:
            return

        # Draw rounded fill
        self.create_arc(
            0, 0, 2 * r, 2 * r, start=90, extent=90, fill=bg, outline="", tags="card_bg"
        )
        self.create_arc(
            w - 2 * r, 0, w, 2 * r, start=0, extent=90, fill=bg, outline="", tags="card_bg"
        )
        self.create_arc(
            w - 2 * r, h - 2 * r, w, h, start=270, extent=90, fill=bg, outline="", tags="card_bg"
        )
        self.create_arc(
            0, h - 2 * r, 2 * r, h, start=180, extent=90, fill=bg, outline="", tags="card_bg"
        )
        self.create_rectangle(r, 0, w - r, h, fill=bg, outline="", tags="card_bg")
        self.create_rectangle(0, r, w, h - r, fill=bg, outline="", tags="card_bg")

        # Draw borders
        if wd > 0:
            self.create_line(r, 0, w - r, 0, fill=outline, width=wd, tags="card_border")
            self.create_line(w, r, w, h - r, fill=outline, width=wd, tags="card_border")
            self.create_line(r, h, w - r, h, fill=outline, width=wd, tags="card_border")

            l_color = self.left_accent if self.left_accent else outline
            self.create_line(
                0,
                r,
                0,
                h - r,
                fill=l_color,
                width=wd if not self.left_accent else wd + 1,
                tags="card_border",
            )

            self.create_arc(
                0,
                0,
                2 * r,
                2 * r,
                start=90,
                extent=90,
                style="arc",
                outline=l_color,
                width=wd,
                tags="card_border",
            )
            self.create_arc(
                w - 2 * r,
                0,
                w,
                2 * r,
                start=0,
                extent=90,
                style="arc",
                outline=outline,
                width=wd,
                tags="card_border",
            )
            self.create_arc(
                w - 2 * r,
                h - 2 * r,
                w,
                h,
                start=270,
                extent=90,
                style="arc",
                outline=outline,
                width=wd,
                tags="card_border",
            )
            self.create_arc(
                0,
                h - 2 * r,
                2 * r,
                h,
                start=180,
                extent=90,
                style="arc",
                outline=l_color,
                width=wd,
                tags="card_border",
            )

        pad = r // 2
        self.itemconfig(self._window_id, x=pad, y=pad, width=w - 2 * pad, height=h - 2 * pad)
