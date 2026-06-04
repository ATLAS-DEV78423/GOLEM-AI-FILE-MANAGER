"""The search popup — a Raycast-style command palette.

Layout
------
::

    ┌──────────────────────────────────────────┐
    │  ⚲  Describe what you're looking for...  │   ← command bar
    ├──────────────────────────────────────────┤
    │  QuarterlyBudget.xlsx       ● Finance    │
    │  Final report, March 2024                │
    ├──────────────────────────────────────────┤
    │  design-spec-v2.pdf         ● Design     │
    │  Figma export, 18 pages                  │
    ├──────────────────────────────────────────┤
    │  ...                                      │
    ├──────────────────────────────────────────┤
    │  ↑↓ navigate   ↵ open   ⌘↵ reveal  esc   │   ← footer hints
    └──────────────────────────────────────────┘

Interaction
-----------
- Type to filter (debounced 250 ms)
- ``↑`` / ``↓`` / ``Home`` / ``End`` to navigate
- ``Return`` to open the highlighted result
- ``Cmd+Return`` (or ``Ctrl+Return``) to reveal in Explorer
- ``Escape`` to hide
- Click outside the popup to hide (the parent window handles this)
"""
from __future__ import annotations

import logging
import queue
import threading
import tkinter as tk
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .ui_anim import fade_in, fade_out_then, slide_in
from .ui_components import (
    FooterHints,
    HoverList,
    _RowSpec,
)
from .ui_icons import get_icon
from .ui_theme import COLORS, ICON_SIZE, SIZE, SPACING, TYPOGRAPHY
from .ui_window import place_at_cursor, strip_window_chrome

_LOG = logging.getLogger(__name__)


@dataclass(slots=True)
class SearchPopupConfig:
    width: int = SIZE.search_popup_w
    height: int = SIZE.search_popup_h
    debounce_ms: int = 250
    min_query_length: int = 0
    placeholder: str = "Describe what you're looking for…"


class SearchPopup:
    """The command-bar style search popup."""

    def __init__(
        self,
        root: tk.Tk,
        on_search: Callable[[str], dict[str, Any]],
        on_open: Callable[[str], None],
        on_reveal: Callable[[str], None],
        on_settings: Callable[[], None] | None = None,
        config: SearchPopupConfig | None = None,
    ):
        self.root = root
        self._on_search = on_search
        self._on_open = on_open
        self._on_reveal_callback = on_reveal
        self._on_settings_callback = on_settings
        self.config = config or SearchPopupConfig()
        self.window: tk.Toplevel | None = None
        self._query: tk.Entry | None = None
        self._query_var: tk.StringVar | None = None
        self._list: HoverList | None = None
        self._list_frame: tk.Frame | None = None
        self._placeholder: str = self.config.placeholder
        self._placeholder_active: bool = True
        self.results: list[dict[str, Any]] = []
        self.message: str = ""
        self.not_found: bool = False
        self._search_after_id: str | None = None
        self._search_generation = 0
        self._latest_rendered_generation = 0
        self._results_queue: queue.Queue[tuple[int, dict[str, Any]]] = queue.Queue()
        self._pump_id: str | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def open(self) -> None:
        if self.window and self.window.winfo_exists():
            try:
                self.window.deiconify()
                self.window.lift()
                if self._query is not None:
                    self._query.focus_set()
                    self._query.select_range(0, tk.END)
            except tk.TclError:
                pass
            return
        win = self._build_window()
        self.window = win
        # Position just below the cursor
        try:
            place_at_cursor(win, self.config.width, self.config.height)
        except Exception:
            win.geometry(f"{self.config.width}x{self.config.height}+100+100")
        # Start hidden, then fade + slide in.
        try:
            win.attributes("-alpha", 0.0)
        except tk.TclError:
            pass
        win.update_idletasks()
        try:
            fade_in(win, duration_ms=180, from_alpha=0.0, to_alpha=1.0)
            slide_in(win, duration_ms=220, from_dy=10)
        except Exception:
            pass
        # Pump results from worker threads.
        self._pump_id = self.root.after(80, self._pump_results)
        if self._query is not None:
            self._query.focus_set()
        self._show_idle_state()

    def hide(self) -> None:
        if not self.window or not self.window.winfo_exists():
            return
        if self._pump_id is not None:
            try:
                self.root.after_cancel(self._pump_id)
            except tk.TclError:
                pass
            self._pump_id = None
        try:
            fade_out_then(self.window, duration_ms=120, then=self._destroy)
        except Exception:
            self._destroy()

    def _destroy(self) -> None:
        if self.window is not None:
            try:
                self.window.destroy()
            except tk.TclError:
                pass
            self.window = None
            self._query = None
            self._list = None

    def toggle(self) -> None:
        if self.window and self.window.winfo_exists():
            self.hide()
        else:
            self.open()

    # ------------------------------------------------------------------
    # Settings shortcut
    # ------------------------------------------------------------------

    def _open_settings(self) -> None:
        if self._on_settings_callback is not None:
            self._on_settings_callback()
        self.hide()

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------

    def _build_window(self) -> tk.Toplevel:
        win = tk.Toplevel(self.root)
        win.title("GOLEM")
        win.configure(bg=COLORS.bg.panel)
        strip_window_chrome(win, hide_titlebar=True)
        win.minsize(self.config.width - 80, 200)
        win.bind("<Escape>", lambda _e: self.hide())
        win.bind("<Control-comma>", lambda _e: self._open_settings())

        outer = tk.Frame(win, bg=COLORS.border.subtle, bd=0, highlightthickness=0)
        outer.pack(fill="both", expand=True)
        # One-px hairline border
        body = tk.Frame(outer, bg=COLORS.bg.panel, bd=0, highlightthickness=0)
        body.pack(fill="both", expand=True, padx=1, pady=1)

        # --- Command bar
        self._build_command_bar(body).pack(fill="x", padx=SPACING.lg, pady=(SPACING.lg, SPACING.sm))

        # --- Divider
        tk.Frame(body, bg=COLORS.border.subtle, height=1).pack(fill="x")

        # --- Results
        self._list_frame = tk.Frame(body, bg=COLORS.bg.panel)
        self._list_frame.pack(fill="both", expand=True, padx=SPACING.md, pady=SPACING.sm)
        self._list = HoverList(
            self._list_frame,
            on_activate=self._on_activate,
            on_reveal=self._on_reveal,
        )
        self._list.build().pack(fill="both", expand=True)

        # --- Footer
        tk.Frame(body, bg=COLORS.border.subtle, height=1).pack(fill="x")
        FooterHints(
            body,
            [
                ("↑↓", "navigate"),
                ("↵", "open"),
                ("⌘↵", "reveal"),
                ("⌘,", "settings"),
                ("esc", "close"),
            ],
        ).pack(fill="x")

        return win

    def _build_command_bar(self, parent: tk.Misc) -> tk.Frame:
        bar = tk.Frame(parent, bg=COLORS.bg.panel)
        # Search icon on the left
        icon_img = get_icon("search", size=ICON_SIZE.md, color=COLORS.fg.tertiary, master=bar)
        icon = tk.Label(
            bar, image=icon_img,
            bg=COLORS.bg.panel,
        )
        icon.image = icon_img  # type: ignore[attr-defined]
        icon.pack(side="left", padx=(0, SPACING.sm))

        self._query_var = tk.StringVar()
        self._query = tk.Entry(
            bar,
            textvariable=self._query_var,
            bg=COLORS.bg.panel, fg=COLORS.fg.primary,
            insertbackground=COLORS.accent.DEFAULT,
            relief="flat", bd=0, highlightthickness=0,
            font=TYPOGRAPHY.body.font(),
        )
        self._query.pack(side="left", fill="x", expand=True, ipady=SPACING.xs)
        self._query.bind("<KeyRelease>", self._on_keyrelease)
        self._query.bind("<Return>", self._on_return)
        self._query.bind("<Shift-Return>", self._on_reveal_key)
        self._query.bind("<Control-Return>", self._on_reveal_key)
        self._query.bind("<Up>", lambda _e: self._list_select(-1))
        self._query.bind("<Down>", lambda _e: self._list_select(1))
        self._query.bind("<Home>", lambda _e: self._list_first())
        self._query.bind("<End>", lambda _e: self._list_last())
        self._query.bind("<Escape>", lambda _e: self._on_escape())
        # Clear button (right side of command bar)
        self._clear_btn_img = get_icon("x", size=12, color=COLORS.fg.tertiary, master=bar)
        self._clear_btn = tk.Label(
            bar, image=self._clear_btn_img,
            bg=COLORS.bg.panel,
            cursor="hand2",
        )
        self._clear_btn.image = self._clear_btn_img  # type: ignore[attr-defined]
        self._clear_btn.pack(side="right", padx=(SPACING.sm, 0))
        self._clear_btn.bind("<Button-1>", lambda _e: self._clear_query())
        self._clear_btn.bind("<Enter>", lambda _e: self._clear_btn.configure(bg=COLORS.bg.hover))
        self._clear_btn.bind("<Leave>", lambda _e: self._clear_btn.configure(bg=COLORS.bg.panel))
        # Placeholder behavior
        self._query_var.set(self._placeholder)
        self._query.configure(foreground=COLORS.fg.tertiary)
        self._placeholder_active = True
        self._query.bind("<FocusIn>", self._on_focus_in)
        self._query.bind("<FocusOut>", self._on_focus_out)
        return bar

    def _clear_query(self) -> None:
        """Clear the search query and show idle state."""
        if self._query_var is not None:
            self._query_var.set("")
        if self._query is not None:
            self._query.focus_set()
        if not self._placeholder_active:
            self._show_idle_state()
        if self._search_after_id is not None:
            try:
                self.root.after_cancel(self._search_after_id)
            except tk.TclError:
                pass
            self._search_after_id = None

    def _on_escape(self) -> None:
        """Clear query on first Escape, close on second."""
        q = self._query_var.get() if self._query_var else ""
        if q and not self._placeholder_active:
            self._clear_query()
        else:
            self.hide()

    # ------------------------------------------------------------------
    # Placeholder behavior
    # ------------------------------------------------------------------

    def _on_focus_in(self, _event: tk.Event) -> None:
        assert self._query_var is not None and self._query is not None
        if self._placeholder_active:
            self._query_var.set("")
            self._query.configure(foreground=COLORS.fg.primary)
            self._placeholder_active = False

    def _on_focus_out(self, _event: tk.Event) -> None:
        assert self._query_var is not None and self._query is not None
        if not self._query_var.get():
            self._query_var.set(self._placeholder)
            self._query.configure(foreground=COLORS.fg.tertiary)
            self._placeholder_active = True

    # ------------------------------------------------------------------
    # Key handling
    # ------------------------------------------------------------------

    def _on_keyrelease(self, event: tk.Event) -> None:
        # Ignore arrow / shift / control / etc.
        if event.keysym in (
            "Up", "Down", "Left", "Right", "Home", "End",
            "Return", "Escape", "Shift_L", "Shift_R", "Control_L", "Control_R",
        ):
            return
        assert self._query_var is not None
        if self._search_after_id is not None:
            try:
                self.root.after_cancel(self._search_after_id)
            except tk.TclError:
                pass
            self._search_after_id = None
        q = self._query_var.get()
        if len(q) >= self.config.min_query_length:
            self._search_after_id = self.root.after(
                self.config.debounce_ms, lambda: self._kick_search(q),
            )
        else:
            self._show_idle_state()

    def _on_return(self, _event: tk.Event) -> str | None:
        assert self._list is not None
        payload = self._list.get_selected_payload()
        if payload is not None:
            self._on_activate(payload)
        return "break"

    def _on_reveal_key(self, _event: tk.Event) -> str | None:
        assert self._list is not None
        payload = self._list.get_selected_payload()
        if payload is not None:
            self._on_reveal(payload)
        return "break"

    def _list_select(self, direction: int) -> None:
        assert self._list is not None
        if direction > 0:
            self._list.select_next()
        else:
            self._list.select_prev()

    def _list_first(self) -> None:
        assert self._list is not None
        self._list.select_first()

    def _list_last(self) -> None:
        assert self._list is not None
        self._list.select_last()

    # ------------------------------------------------------------------
    # Search dispatch
    # ------------------------------------------------------------------

    def _kick_search(self, query: str) -> None:
        self._search_generation += 1
        generation = self._search_generation
        # Show shimmer skeleton loading state
        if not self.results:
            assert self._list is not None
            self._list.show_shimmer()

        def worker() -> None:
            try:
                payload = self._on_search(query)
            except Exception as exc:
                payload = {"status": "error", "results": [], "message": str(exc)}
            if not isinstance(payload, dict):
                payload = {"status": "error", "results": [], "message": "Invalid response"}
            self._results_queue.put((generation, payload))

        threading.Thread(target=worker, daemon=True, name="golem-search").start()

    def _pump_results(self) -> None:
        try:
            while True:
                generation, payload = self._results_queue.get_nowait()
                if generation >= self._latest_rendered_generation:
                    self._latest_rendered_generation = generation
                    self.show_results(payload)
        except queue.Empty:
            pass
        self._pump_id = self.root.after(80, self._pump_results)

    # ------------------------------------------------------------------
    # Render results
    # ------------------------------------------------------------------

    def show_results(self, payload: dict[str, Any]) -> None:
        assert self._list is not None
        self.results = list(payload.get("results", []))
        self.message = str(payload.get("message", "") or "")
        status = payload.get("status", "ok")
        rows = [self._to_row(r) for r in self.results]
        if not rows:
            if status == "error":
                self._list.show_empty("alert", "Search failed", self.message or "Try a different query.")
            elif self.message:
                self._list.show_empty("search", "No matches", self.message)
            else:
                self._list.show_empty("search", "No results", "Try different keywords.")
        else:
            self._list.set_rows(rows)
            # Auto-select first result for keyboard nav
            self._list.select_first()

    def _to_row(self, r: dict[str, Any]) -> _RowSpec:
        primary = r.get("clean_filename") or r.get("original_filename") or "(unnamed)"
        secondary = r.get("summary") or ""
        category = r.get("category") or ""
        confidence = r.get("confidence")
        tertiary = ""
        if confidence is not None and confidence != "":
            try:
                tertiary = f"{float(confidence) * 100:.0f}%"
            except (TypeError, ValueError):
                pass
        badge = None
        if category:
            color = getattr(COLORS.category, category.lower(), COLORS.category.other)
            badge = (category, color)
        return _RowSpec(
            primary=str(primary),
            secondary=str(secondary),
            tertiary=tertiary,
            badge=badge,
            payload=r.get("current_path") or r.get("original_path") or "",
        )

    def _show_idle_state(self) -> None:
        assert self._list is not None
        if not self.results:
            self._list.show_empty(
                "search",
                "Search your vault",
                "Drop a file into the watched folder to start. Press Esc to close.",
            )

    def set_status(self, message: str) -> None:
        # The status bar moved to the bottom of the search popup via
        # the FooterHints row; this method is kept for backward compat.
        if not message or self._query_var is None or self._query is None:
            return
        # Update placeholder text with the message as a hint.
        if not self._query_var.get() or self._placeholder_active:
            try:
                self._query_var.set(message)
                self._query.configure(foreground=COLORS.fg.tertiary)
                self._placeholder_active = False
            except tk.TclError:
                pass

    # ------------------------------------------------------------------
    # Activation
    # ------------------------------------------------------------------

    def _on_activate(self, payload: Any) -> None:
        path = str(payload)
        if path:
            self._on_open(path)
            self.hide()

    def _on_reveal(self, payload: Any) -> None:
        path = str(payload)
        if path:
            self._on_reveal_callback(path)
            self.hide()
