"""The GOLEM launcher — a beautiful floating search window.

Pure search, nothing else. No sidebar, no graph, no clusters. Every pixel
serves the search experience. Matches the visual spec: dark surface with
orange accent, solid orange selected state, emoji file icons, grouped
results, term highlighting, and three precise animations.

Layout
------
::

    ┌──────────────────────────────────────────────┐
    │  🔍  Describe what you're looking for…   esc │  ← search box
    ├──────────────────────────────────────────────┤
    │  FILES                         (section)     │
    │  📄 Pricing Strategy Q3 2024.pdf   both      │  ← result items
    │     ~/Documents/Business/...                  │
    │     Value metric pricing outperforms…         │
    ├──────────────────────────────────────────────┤
    │  ● 4,218 files · indexed just now   ↑↓ ↵ esc │  ← footer bar
    └──────────────────────────────────────────────┘
"""

from __future__ import annotations

import logging
import queue
import threading
import tkinter as tk
import tkinter.ttk as ttk
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from .ui_anim import fade_out_then, launcher_open
from .ui_components import (
    file_type_emoji,
    file_type_from_name,
)
from .ui_theme import COLORS, SIZE, SPACING
from .ui_window import place_at_cursor

_LOG = logging.getLogger(__name__)

# ── SearchResult dataclass (matches backend + UI spec) ──────────────


@dataclass(slots=True)
class SearchResult:
    """A single search result, matching the spec's SearchResult fields."""

    file_path: str = ""
    file_name: str = ""
    file_type: str = ""
    snippet: str = ""
    match_type: str = ""
    matched_terms: list[str] = field(default_factory=list)
    modified_at: str = ""
    group: str = "FILES"


def _truncate_path(path: str, max_len: int = 48) -> str:
    """Truncate a path with ellipsis on the left: …/Meetings/file.md"""
    if len(path) <= max_len:
        return path
    return "…" + path[-(max_len - 1) :]


# ── SearchPopupConfig ──────────────────────────────────────────────


@dataclass(slots=True)
class SearchPopupConfig:
    width: int = SIZE.search_popup_w
    height: int = SIZE.search_popup_h
    debounce_ms: int = 150  # per spec: 150ms
    min_query_length: int = 2  # per spec: 2 characters
    placeholder: str = "Describe what you're looking for\u2026"
    max_visible_results: int = 8  # per spec: 8 items before scroll
    max_window_height: int = 560  # per spec
    top_k: int = 8


# ── SearchPopup (the launcher) ─────────────────────────────────────


class SearchPopup:
    """The GOLEM launcher — a pure, beautiful floating search window."""

    def __init__(
        self,
        root: tk.Tk,
        on_search: Callable[[str, int], list[dict[str, Any]]],
        on_open: Callable[[str], None] | None = None,
        on_reveal: Callable[[str], None] | None = None,
        config: SearchPopupConfig | None = None,
    ):
        self.root = root
        self._on_search = on_search
        self._on_open = on_open or (lambda p: None)
        self._on_reveal_callback = on_reveal or (lambda p: None)
        self.config = config or SearchPopupConfig()

        # Window state
        self.window: tk.Toplevel | None = None

        # Search state
        self._query_var: tk.StringVar | None = None
        self._query: tk.Entry | None = None
        self._results_canvas: tk.Canvas | None = None
        self._results_frame: tk.Frame | None = None
        self._scrollbar: ttk.Scrollbar | None = None
        self._status_label: tk.Label | None = None
        self._hints_label: tk.Label | None = None

        # Data
        self.results: list[SearchResult] = []
        self._selected_idx: int = -1
        self._placeholder_active: bool = True

        # Search debounce + threading
        self._search_after_id: str | None = None
        self._search_generation: int = 0
        self._results_queue: queue.Queue[tuple[int, list[SearchResult]]] = queue.Queue()
        self._pump_id: str | None = None

        # Scroll state
        self._scroll_offset: int = 0
        self._items_per_page: int = self.config.max_visible_results

    # ── Lifecycle ──────────────────────────────────────────────────

    def open(self) -> None:
        if self.window and self.window.winfo_exists():
            try:
                self.window.deiconify()
                self.window.lift()
                self.window.focus_set()
                if self._query is not None:
                    self._query.focus_set()
                    self._query.select_range(0, tk.END)
            except tk.TclError:
                pass
            return

        win = self._build_window()
        self.window = win
        try:
            place_at_cursor(win, self.config.width, self.config.height)
        except Exception:
            win.geometry(f"{self.config.width}x{self.config.height}+100+100")
        win.update_idletasks()

        # Launch animation (per spec: scale + fade, 120ms)
        try:
            launcher_open(win, duration_ms=120)
        except Exception:
            try:
                win.attributes("-alpha", 1.0)
            except tk.TclError:
                pass

        self._pump_id = self.root.after(80, self._pump_results)

        if self._query is not None:
            self._query.focus_set()
            self._query.icursor(tk.END)

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
            fade_out_then(self.window, duration_ms=80, then=self._destroy)
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
            self._results_canvas = None
            self._results_frame = None

    def toggle(self) -> None:
        if self.window and self.window.winfo_exists():
            self.hide()
        else:
            self.open()

    # ── Build ──────────────────────────────────────────────────────

    def _build_window(self) -> tk.Toplevel:
        win = tk.Toplevel(self.root)
        win.title("GOLEM")
        win.configure(bg=COLORS.bg.canvas)
        win.overrideredirect(True)
        try:
            win.attributes("-topmost", True)
        except tk.TclError:
            pass

        win.minsize(self.config.width, SIZE.search_popup_min_h)
        win.maxsize(self.config.width, self.config.max_window_height)
        win.resizable(False, True)

        win.bind("<Escape>", lambda _e: self._on_escape())

        # Outer container with orange rim + shadow
        outer = tk.Frame(win, bg=COLORS.bg.canvas, bd=0, highlightthickness=0)
        outer.pack(fill="both", expand=True)

        # The launcher surface — #111111 with 14px radius
        surface = tk.Frame(outer, bg=COLORS.bg.panel, bd=0, highlightthickness=0)
        surface.pack(fill="both", expand=True, padx=1, pady=1)

        # ── Search Box ──
        self._build_search_box(surface)

        # ── Divider ──
        tk.Frame(surface, bg=COLORS.border.subtle, height=1).pack(fill="x")

        # ── Results area (scrollable canvas) ──
        results_outer = tk.Frame(surface, bg=COLORS.bg.panel)
        results_outer.pack(fill="both", expand=True)

        self._results_canvas = tk.Canvas(
            results_outer,
            bg=COLORS.bg.panel,
            bd=0,
            highlightthickness=0,
            takefocus=0,
        )
        self._scrollbar = ttk.Scrollbar(
            results_outer,
            orient="vertical",
            command=self._on_scrollbar,
            style="Vertical.TScrollbar",
        )
        self._results_canvas.configure(yscrollcommand=self._scrollbar.set)
        self._results_canvas.pack(side="left", fill="both", expand=True)
        self._scrollbar.pack(side="right", fill="y")

        # Frame inside canvas for results
        self._results_frame = tk.Frame(self._results_canvas, bg=COLORS.bg.panel)
        self._window_id = self._results_canvas.create_window(
            0,
            0,
            window=self._results_frame,
            anchor="nw",
            tags="inner",
        )

        def _configure_inner(_e: tk.Event) -> None:
            # Guard against teardown races: _results_canvas / _window_id can
            # be None'd out by SearchPopup.hide() before Tk fires a final
            # <Configure>. Dereferencing None here would propagate into
            # Tk's C-level error handler and permanently desync the
            # scrollbar. Also cache locally so the same teardown can't
            # race between the None-check and the itemconfig call.
            canvas = self._results_canvas
            wid = self._window_id
            if canvas is None or wid is None:
                return
            canvas.itemconfig(wid, width=canvas.winfo_width())

        self._results_canvas.bind("<Configure>", _configure_inner)
        self._results_frame.bind("<Configure>", self._on_frame_configure)

        # Mousewheel scrolling
        self._results_canvas.bind("<MouseWheel>", self._on_mousewheel)
        self._results_canvas.bind("<Button-4>", lambda e: self._on_mousewheel(e))
        self._results_canvas.bind("<Button-5>", lambda e: self._on_mousewheel(e))

        # ── Footer bar ──
        self._build_footer(surface)

        return win

    def _build_search_box(self, parent: tk.Misc) -> None:
        """Build the search box per spec: orange border, glow, 52px height."""
        search_frame = tk.Frame(parent, bg=COLORS.bg.panel, height=SIZE.input_height)
        search_frame.pack(fill="x", padx=SPACING.lg, pady=(SPACING.lg, SPACING.md))
        search_frame.pack_propagate(False)

        # Search icon (magnifier)
        from .ui_icons import get_icon

        icon_img = get_icon("search", size=18, color=COLORS.accent.DEFAULT, master=search_frame)
        icon_lbl = tk.Label(search_frame, image=icon_img, bg=COLORS.bg.panel, cursor="xterm")
        icon_lbl.image = icon_img  # type: ignore[attr-defined]
        icon_lbl.pack(side="left", padx=(0, SPACING.sm))

        # Search entry — custom tk.Entry with orange border + glow
        self._query_var = tk.StringVar()
        self._query = tk.Entry(
            search_frame,
            textvariable=self._query_var,
            bg=COLORS.bg.input,
            fg=COLORS.fg.primary,
            insertbackground=COLORS.accent.DEFAULT,
            insertwidth=2,
            relief="flat",
            highlightthickness=2,
            highlightbackground=COLORS.accent.DEFAULT,  # orange border always
            highlightcolor=COLORS.accent.DEFAULT,
            bd=0,
            font=("Segoe UI", 15, "normal"),
            selectbackground=COLORS.accent.muted,
            selectforeground=COLORS.fg.primary,
        )
        self._query.pack(side="left", fill="x", expand=True, ipady=4)

        # Placeholder behavior
        self._query_var.set(self.config.placeholder)
        self._query.configure(foreground=COLORS.fg.tertiary)
        self._placeholder_active = True
        self._query.bind("<FocusIn>", self._on_focus_in)
        self._query.bind("<FocusOut>", self._on_focus_out)

        # Key handling
        self._query.bind("<KeyRelease>", self._on_keyrelease)
        self._query.bind("<Return>", self._on_return)
        self._query.bind("<Control-Return>", self._on_reveal_key)
        self._query.bind("<Up>", lambda _e: self._select(-1))
        self._query.bind("<Down>", lambda _e: self._select(1))
        self._query.bind("<Home>", lambda _e: self._select_first())
        self._query.bind("<End>", lambda _e: self._select_last())
        self._query.bind("<Escape>", lambda _e: self._on_escape())

        # Shortcut badge (ESC to close)
        from .ui_components import KeyboardHint

        hint = KeyboardHint(search_frame, "esc", style="Kbd.TLabel")
        hint.pack(side="right", padx=(SPACING.sm, 0))

    def _build_footer(self, parent: tk.Misc) -> None:
        """Build the footer bar per spec: 32px, status left, hints right."""
        footer = tk.Frame(parent, bg=COLORS.bg.panel, height=SIZE.statusbar_height)
        footer.pack(fill="x", side="bottom")
        footer.pack_propagate(False)

        # Thin top border
        tk.Frame(footer, bg=COLORS.border.subtle, height=1).pack(fill="x")

        inner = tk.Frame(footer, bg=COLORS.bg.panel)
        inner.pack(fill="both", expand=True, padx=SPACING.lg)

        # Left: index status
        status_frame = tk.Frame(inner, bg=COLORS.bg.panel)
        status_frame.pack(side="left")
        # Green dot
        dot_canvas = tk.Canvas(
            status_frame, width=8, height=8, bg=COLORS.bg.panel, highlightthickness=0, bd=0
        )
        dot_canvas.create_oval(1, 1, 7, 7, fill="#22c55e", outline="")
        dot_canvas.pack(side="left", padx=(0, SPACING.xs))
        self._status_label = tk.Label(
            status_frame,
            text="\u25cf 4,218 files \u00b7 indexed just now",
            font=("Consolas", 11, "normal"),
            fg=COLORS.fg.tertiary,
            bg=COLORS.bg.panel,
        )
        self._status_label.pack(side="left")

        # Right: key hints
        self._hints_label = tk.Label(
            inner,
            text="\u2191\u2193 navigate  \u00b7  \u21b5 open  \u00b7  esc close",
            font=("Consolas", 11, "normal"),
            fg=COLORS.fg.tertiary,
            bg=COLORS.bg.panel,
        )
        self._hints_label.pack(side="right")

    # ── Placeholder ────────────────────────────────────────────────

    def _on_focus_in(self, _event: tk.Event) -> None:
        if self._query is None or self._query_var is None:
            return
        if self._placeholder_active:
            self._query_var.set("")
            self._query.configure(foreground=COLORS.fg.primary)
            self._placeholder_active = False

    def _on_focus_out(self, _event: tk.Event) -> None:
        if self._query is None or self._query_var is None:
            return
        if not self._query_var.get():
            self._query_var.set(self.config.placeholder)
            self._query.configure(foreground=COLORS.fg.tertiary)
            self._placeholder_active = True

    # ── Escape: clear then close ───────────────────────────────────

    def _on_escape(self) -> None:
        if self._query_var is None:
            self.hide()
            return
        q = self._query_var.get()
        if q and not self._placeholder_active:
            self._clear_query()
        else:
            self.hide()

    def _clear_query(self) -> None:
        if self._query_var is not None:
            self._query_var.set("")
        if self._query is not None:
            self._query.focus_set()
        self._show_idle_state()
        if self._search_after_id is not None:
            try:
                self.root.after_cancel(self._search_after_id)
            except tk.TclError:
                pass
            self._search_after_id = None

    # ── Key handling ───────────────────────────────────────────────

    def _on_keyrelease(self, event: tk.Event) -> None:
        if event.keysym in (
            "Up",
            "Down",
            "Left",
            "Right",
            "Home",
            "End",
            "Return",
            "Escape",
            "Shift_L",
            "Shift_R",
            "Control_L",
            "Control_R",
        ):
            return
        if self._query_var is None:
            return
        if self._search_after_id is not None:
            try:
                self.root.after_cancel(self._search_after_id)
            except tk.TclError:
                pass
            self._search_after_id = None
        q = self._query_var.get()
        if len(q) >= self.config.min_query_length and not self._placeholder_active:
            self._search_after_id = self.root.after(
                self.config.debounce_ms,
                lambda: self._kick_search(q),
            )
        else:
            self._show_idle_state()

    def _on_return(self, _event: tk.Event) -> str | None:
        if 0 <= self._selected_idx < len(self.results):
            result = self.results[self._selected_idx]
            if result.file_path:
                self._on_open(result.file_path)
                self.hide()
        return "break"

    def _on_reveal_key(self, _event: tk.Event) -> str | None:
        if 0 <= self._selected_idx < len(self.results):
            result = self.results[self._selected_idx]
            if result.file_path:
                self._on_reveal_callback(result.file_path)
                self.hide()
        return "break"

    def _select(self, direction: int) -> None:
        if not self.results:
            return
        n = len(self.results)
        self._selected_idx = (self._selected_idx + direction) % n
        self._render_results()
        self._ensure_visible()

    def _select_first(self) -> None:
        if self.results:
            self._selected_idx = 0
            self._render_results()
            self._ensure_visible()

    def _select_last(self) -> None:
        if self.results:
            self._selected_idx = len(self.results) - 1
            self._render_results()
            self._ensure_visible()

    def _ensure_visible(self) -> None:
        """Scroll to keep selected item visible."""
        if self._results_canvas is None:
            return
        if self._selected_idx < self._scroll_offset:
            self._scroll_offset = max(0, self._selected_idx)
        elif self._selected_idx >= self._scroll_offset + self._items_per_page - 1:
            self._scroll_offset = min(
                max(0, len(self.results) - self._items_per_page),
                self._selected_idx - self._items_per_page + 2,
            )
        self._sync_scrollbar()
        self._render_results()

    # ── Scrollbar ──────────────────────────────────────────────────

    def _on_scrollbar(self, *args: Any) -> None:
        if args[0] == "moveto":
            frac = float(args[1])
            max_offset = max(0, len(self.results) - self._items_per_page)
            self._scroll_offset = int(round(frac * max_offset))
            self._render_results()
        elif args[0] == "scroll":
            amount = int(args[1])
            self._scroll_offset = max(
                0,
                min(
                    self._scroll_offset + amount,
                    max(0, len(self.results) - self._items_per_page),
                ),
            )
            self._render_results()

    def _sync_scrollbar(self) -> None:
        if self._scrollbar is None:
            return
        total = max(1, len(self.results))
        max_offset = max(0, total - self._items_per_page)
        if max_offset > 0:
            frac = self._scroll_offset / max_offset
            view = min(1.0, self._items_per_page / total)
            self._scrollbar.set(frac, min(1.0, frac + view))
        else:
            self._scrollbar.set(0.0, 1.0)

    def _on_mousewheel(self, event: tk.Event) -> None:
        delta = (
            -1
            if event.delta > 0
            else 1
            if hasattr(event, "delta")
            else (-1 if event.num == 4 else 1)
        )
        self._scroll_offset = max(
            0,
            min(
                self._scroll_offset + delta * 3,
                max(0, len(self.results) - self._items_per_page),
            ),
        )
        self._render_results()
        self._sync_scrollbar()

    def _on_frame_configure(self, _event: tk.Event | None = None) -> None:
        if self._results_canvas is not None:
            self._results_canvas.configure(
                scrollregion=self._results_canvas.bbox("all"),
            )

    # ── Search dispatch ────────────────────────────────────────────

    def _kick_search(self, query: str) -> None:
        self._search_generation += 1
        generation = self._search_generation

        def worker() -> None:
            try:
                raw_results = self._on_search(query, self.config.top_k)
                results = self._dicts_to_results(raw_results)
            except Exception as exc:
                _LOG.warning("Search failed: %s", exc)
                results = []
            self._results_queue.put((generation, results))

        threading.Thread(target=worker, daemon=True, name="golem-search").start()

    def _dicts_to_results(self, raw: list[dict[str, Any]]) -> list[SearchResult]:
        """Convert backend dicts to SearchResult objects."""
        out: list[SearchResult] = []
        for r in raw:
            name = str(r.get("clean_filename") or r.get("original_filename") or "")
            ftype = file_type_from_name(name)
            out.append(
                SearchResult(
                    file_path=str(r.get("current_path") or r.get("original_path") or ""),
                    file_name=name,
                    file_type=ftype,
                    snippet=str(r.get("chunk_text") or r.get("summary") or ""),
                    match_type=str(r.get("match_type") or ""),
                    matched_terms=r.get(
                        "matched_terms",
                        r.get("match_type", "").split(",") if r.get("match_type") else [],
                    ),
                    modified_at=str(r.get("modified_at") or ""),
                    group=str(r.get("group") or (r.get("category") or "FILES").upper()),
                )
            )
        return out

    def _pump_results(self) -> None:
        try:
            while True:
                generation, results = self._results_queue.get_nowait()
                if generation >= self._search_generation:
                    self.results = results
                    self._selected_idx = 0 if results else -1
                    self._scroll_offset = 0
                    self._render_results()
        except queue.Empty:
            pass
        self._pump_id = self.root.after(80, self._pump_results)

    # ── Render results ─────────────────────────────────────────────

    def _render_results(self) -> None:
        """Render results as grouped section labels + items on the canvas."""
        if self._results_frame is None or self._results_canvas is None:
            return

        # Destroy previous children
        for w in list(self._results_frame.winfo_children()):
            w.destroy()

        if not self.results:
            self._show_idle_state()
            return

        # Group results by their `group` field
        groups: dict[str, list[SearchResult]] = {}
        order: list[str] = []
        for r in self.results:
            g = r.group or "FILES"
            if g not in groups:
                groups[g] = []
                order.append(g)
            groups[g].append(r)

        # If all results are the same group, skip section labels (per spec)
        show_labels = len(order) > 1

        max_visible = self._items_per_page

        # Only render items within the scroll window
        visible_start = self._scroll_offset
        visible_end = min(len(self.results), self._scroll_offset + max_visible + 1)

        # Build widgets for visible items
        current_global = 0
        for group_name in order:
            group_items = groups[group_name]

            for gi_idx, item in enumerate(group_items):
                if current_global < visible_start:
                    current_global += 1
                    continue
                if current_global > visible_end:
                    current_global += 1
                    break

                # Section label before first item of each group (if showing labels)
                if show_labels and gi_idx == 0 and current_global <= visible_end:
                    label_frame = tk.Frame(self._results_frame, bg=COLORS.bg.panel)
                    label_frame.pack(fill="x", padx=SPACING.lg, pady=(SPACING.sm, SPACING.xxs))
                    lbl = tk.Label(
                        label_frame,
                        text=group_name.upper(),
                        font=("Consolas", 10, "normal"),
                        fg="#f97316",
                        bg=COLORS.bg.panel,
                    )
                    lbl.pack(anchor="w")

                is_selected = current_global == self._selected_idx
                self._render_result_item(item, is_selected, current_global)
                current_global += 1

        # Update scroll region
        self._results_frame.update_idletasks()
        self._results_canvas.configure(scrollregion=self._results_canvas.bbox("all"))

        # Update footer status
        self._update_footer_status()

    def _render_result_item(self, item: SearchResult, is_selected: bool, idx: int) -> None:
        """Render a single result item as a themed frame."""
        frame = tk.Frame(self._results_frame, bg=COLORS.bg.panel)
        frame.pack(fill="x", padx=SPACING.md, pady=1)

        # Item container with hover/selected background
        item_frame = tk.Frame(frame, bg=COLORS.bg.panel, bd=0, highlightthickness=0)
        item_frame.pack(fill="x", ipadx=SPACING.sm, ipady=SPACING.sm)

        if is_selected:
            item_frame.configure(bg=COLORS.accent.DEFAULT)  # solid orange
            fg_primary = "#ffffff"
            fg_secondary = "#f5e8dc"  # warm white on orange bg
            fg_highlight = "#ffffff"
        else:
            fg_primary = COLORS.fg.primary
            fg_secondary = COLORS.fg.secondary
            fg_highlight = COLORS.accent.DEFAULT

        # ── Row layout ──
        row_top = tk.Frame(item_frame, bg=item_frame["bg"])
        row_top.pack(fill="x", padx=SPACING.sm, pady=(SPACING.xs, 0))

        # File icon (emoji)
        emoji = file_type_emoji(item.file_type)
        icon_frame = tk.Frame(row_top, bg=item_frame["bg"])
        icon_frame.pack(side="left", padx=(0, SPACING.sm))
        icon_lbl = tk.Label(
            icon_frame,
            text=emoji,
            font=("Segoe UI", 13, "normal"),
            bg=item_frame["bg"],
            fg=fg_primary,
        )
        icon_lbl.pack()

        # File name + path (vertical)
        text_col = tk.Frame(row_top, bg=item_frame["bg"])
        text_col.pack(side="left", fill="x", expand=True)

        # File name with term highlighting
        name_lbl = self._make_highlighted_label(
            text_col,
            item.file_name,
            item.matched_terms,
            is_selected,
            fg_primary,
            fg_highlight,
        )
        name_lbl.pack(anchor="w")

        # File path (truncated, mono, muted)
        if item.file_path:
            path_text = _truncate_path(item.file_path)
            path_lbl = tk.Label(
                text_col,
                text=path_text,
                font=("Consolas", 10, "normal"),
                fg=fg_secondary if not is_selected else "#f0dcc8",
                bg=item_frame["bg"],
            )
            path_lbl.pack(anchor="w")

        # Right side: match pill
        if item.match_type:
            pill_frame = tk.Frame(row_top, bg=item_frame["bg"])
            pill_frame.pack(side="right", padx=(SPACING.sm, 0))

            pill_style = {
                "keyword": ("#2d1d12", "#f97316", "#4b2a12"),
                "semantic": ("#222222", "#7a7370", "#292929"),
                "both": ("#3b2312", "#f97316", "#623313"),
                "entity": ("#222222", "#7a7370", "#292929"),
                "temporal": ("#222222", "#7a7370", "#292929"),
            }
            mt = item.match_type.lower()
            if is_selected:
                pill_bg = "#fa8f45"
                pill_fg = "#ffffff"
                pill_border = "#fba468"
            else:
                pbg, pfg, pbdr = pill_style.get(mt, pill_style["semantic"])
                pill_bg = pbg
                pill_fg = pfg
                pill_border = pbdr

            # Draw pill on a tiny canvas
            pill_canvas = tk.Canvas(
                pill_frame, width=60, height=20, bg=item_frame["bg"], highlightthickness=0, bd=0
            )
            pill_canvas.pack()
            label = item.match_type.upper()
            pw = max(42, len(label) * 6 + 16)
            pill_canvas.configure(width=pw)
            pill_canvas.create_rectangle(0, 0, pw, 20, fill=pill_bg, outline=pill_border, width=1)
            pill_canvas.create_text(
                pw // 2,
                10,
                text=label,
                fill=pill_fg,
                font=("Consolas", 9, "normal"),
                anchor="center",
            )

        # ── Bottom row: snippet ──
        if item.snippet:
            snippet_text = item.snippet[:100] + ("\u2026" if len(item.snippet) > 100 else "")
            snippet_lbl = self._make_highlighted_label(
                item_frame,
                snippet_text,
                item.matched_terms,
                is_selected,
                fg_secondary if not is_selected else "#f0dcc8",
                fg_highlight if not is_selected else "#ffffff",
            )
            snippet_lbl.pack(anchor="w", padx=SPACING.sm, pady=(0, SPACING.xxs))

        # Hover effects
        if not is_selected:

            def _on_enter(e: tk.Event, f=item_frame, bg=COLORS.bg.hover) -> None:
                f.configure(bg=bg)
                for c in f.winfo_children():
                    try:
                        c.configure(bg=bg)
                        for cc in c.winfo_children():
                            try:
                                cc.configure(bg=bg)
                                for ccc in cc.winfo_children():
                                    try:
                                        ccc.configure(bg=bg)
                                    except tk.TclError:
                                        pass
                            except tk.TclError:
                                pass
                    except tk.TclError:
                        pass

            def _on_leave(e: tk.Event, f=item_frame, bg=COLORS.bg.panel) -> None:
                f.configure(bg=bg)
                for c in f.winfo_children():
                    try:
                        c.configure(bg=bg)
                        for cc in c.winfo_children():
                            try:
                                cc.configure(bg=bg)
                                for ccc in cc.winfo_children():
                                    try:
                                        ccc.configure(bg=bg)
                                    except tk.TclError:
                                        pass
                            except tk.TclError:
                                pass
                    except tk.TclError:
                        pass

            frame.bind("<Enter>", _on_enter)
            frame.bind("<Leave>", _on_leave)

    def _make_highlighted_label(
        self,
        parent: tk.Misc,
        text: str,
        matched_terms: list[str],
        is_selected: bool,
        fg_default: str,
        fg_highlight: str,
    ) -> tk.Frame:
        """Create a label frame with matched terms highlighted in the accent color."""
        frame = tk.Frame(
            parent, bg=parent["bg"] if hasattr(parent, "__getitem__") else COLORS.bg.panel
        )

        if not matched_terms:
            lbl = tk.Label(
                frame,
                text=text,
                font=("Segoe UI", 13, "normal" if not is_selected else "bold"),
                fg=fg_default,
                bg=frame["bg"],
                anchor="w",
            )
            lbl.pack(anchor="w")
            return frame

        # Simple highlight: split by matched terms and create colored segments
        # This is a simplified approach - for a full implementation, use regex
        import re

        terms = [t for t in matched_terms if t]
        if not terms:
            lbl = tk.Label(
                frame,
                text=text,
                font=("Segoe UI", 13, "normal"),
                fg=fg_default,
                bg=frame["bg"],
                anchor="w",
            )
            lbl.pack(anchor="w")
            return frame

        # Build pattern
        pattern = "|".join(re.escape(t) for t in terms)
        parts = re.split(f"({pattern})", text, flags=re.IGNORECASE) if terms else [text]

        for part in parts:
            is_match = any(t.lower() in part.lower() for t in terms) and part
            if not part:
                continue
            lbl = tk.Label(
                frame,
                text=part,
                font=("Segoe UI", 13, "bold" if is_match else "normal"),
                fg=fg_highlight if is_match else fg_default,
                bg=frame["bg"],
            )
            lbl.pack(side="left")
        return frame

    # ── Empty / idle state ─────────────────────────────────────────

    def _show_idle_state(self) -> None:
        """Show the idle state (no results yet)."""
        if self._results_frame is None:
            return
        for w in list(self._results_frame.winfo_children()):
            w.destroy()

        if self._query_var is not None:
            q = self._query_var.get()
            if len(q) >= self.config.min_query_length and not self._placeholder_active:
                # "Nothing found" state
                self._show_empty_state(
                    "Nothing found",
                    "Try describing the contents, not the filename",
                )
                return

        # Default idle: big welcome message
        center = tk.Frame(self._results_frame, bg=COLORS.bg.panel)
        center.place(relx=0.5, rely=0.45, anchor="center")

        icon_img = None
        try:
            from .ui_icons import get_icon

            icon_img = get_icon("search", size=32, color=COLORS.fg.tertiary, master=center)
        except Exception:
            pass

        if icon_img:
            icon_lbl = tk.Label(center, image=icon_img, bg=COLORS.bg.panel)
            icon_lbl.image = icon_img  # type: ignore[attr-defined]
            icon_lbl.pack(pady=(0, SPACING.md))
        else:
            tk.Label(
                center,
                text="\U0001f50d",
                font=("Segoe UI", 24),
                bg=COLORS.bg.panel,
                fg=COLORS.fg.tertiary,
            ).pack(pady=(0, SPACING.md))

        tk.Label(
            center,
            text="Describe what you're looking for",
            font=("Segoe UI", 14, "normal"),
            fg=COLORS.fg.secondary,
            bg=COLORS.bg.panel,
        ).pack()

        tk.Label(
            center,
            text="GOLEM searches by meaning, not just filenames",
            font=("Segoe UI", 11, "normal"),
            fg=COLORS.fg.tertiary,
            bg=COLORS.bg.panel,
        ).pack(pady=(SPACING.sm, 0))

        self._update_footer_status()

    def _show_empty_state(self, headline: str, body: str) -> None:
        """Show a minimal empty state per spec."""
        if self._results_frame is None:
            return
        for w in list(self._results_frame.winfo_children()):
            w.destroy()

        center = tk.Frame(self._results_frame, bg=COLORS.bg.panel)
        center.place(relx=0.5, rely=0.45, anchor="center")

        try:
            from .ui_icons import get_icon

            icon_img = get_icon("search", size=32, color=COLORS.fg.tertiary, master=center)
            icon_lbl = tk.Label(center, image=icon_img, bg=COLORS.bg.panel)
            icon_lbl.image = icon_img  # type: ignore[attr-defined]
            icon_lbl.pack(pady=(0, SPACING.md))
        except Exception:
            tk.Label(center, text="\U0001f50d", font=("Segoe UI", 24), bg=COLORS.bg.panel).pack(
                pady=(0, SPACING.md)
            )

        tk.Label(
            center,
            text=headline,
            font=("Segoe UI", 14, "normal"),
            fg=COLORS.fg.secondary,
            bg=COLORS.bg.panel,
        ).pack()
        tk.Label(
            center,
            text=body,
            font=("Segoe UI", 11, "normal"),
            fg=COLORS.fg.tertiary,
            bg=COLORS.bg.panel,
        ).pack(pady=(SPACING.xs, 0))

        self._update_footer_status()

    def _update_footer_status(self) -> None:
        """Update the status label with result count."""
        if self._status_label is None:
            return
        n = len(self.results)
        if n == 0:
            self._status_label.configure(text="\u25cf ready  \u00b7  describe what you need")
        else:
            self._status_label.configure(
                text=f"\u25cf {n} result{'s' if n != 1 else ''}  \u00b7  \u2191\u2193 navigate  \u00b7  \u21b5 open",
            )

    # ── Public API ─────────────────────────────────────────────────

    def set_status(self, message: str) -> None:
        """Set a transient status message in the search bar."""
        if not message or self._query_var is None or self._query is None:
            return
        if not self._query_var.get() or self._placeholder_active:
            try:
                self._query_var.set(message)
                self._query.configure(foreground=COLORS.fg.tertiary)
                self._placeholder_active = False
            except tk.TclError:
                pass

    def show_results(self, payload: dict[str, Any]) -> None:
        """Receive search results from the legacy pipeline."""
        raw = payload.get("results", [])
        self.results = self._dicts_to_results(raw) if raw else []
        self._selected_idx = 0 if self.results else -1
        self._scroll_offset = 0
        self._render_results()
