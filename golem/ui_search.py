"""The search popup — a Raycast-style command palette with chat-over-files.

Layout
------
::

    ┌──────────────────────────────────────────┐
    │  ⚲  Describe what you're looking for…   │   ← command bar
    │  🔍  💬                                 │   ← mode toggle
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

In chat mode (💬 active), the input becomes a question box. Pressing Enter
sends the question to the LLM and displays the answer + supporting files.
"""
from __future__ import annotations

import logging
import queue
import threading
import tkinter as tk
import tkinter.ttk as ttk
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .ui_anim import fade_in, fade_out_then, slide_in
from .ui_components import (
    FooterHints,
    HoverList,
    RoundedCard,
    _RowSpec,
)
from .ui_icons import get_icon
from .ui_theme import COLORS, ICON_SIZE, SIZE, SPACING, TYPOGRAPHY
from .ui_window import place_at_cursor, strip_window_chrome
from .utils import text_excerpt

_LOG = logging.getLogger(__name__)


@dataclass(slots=True)
class SearchPopupConfig:
    width: int = SIZE.search_popup_w
    height: int = SIZE.search_popup_h
    debounce_ms: int = 250
    min_query_length: int = 0
    placeholder: str = "Search for apps, files, and more..."
    chat_placeholder: str = "Ask a question about your files\u2026"


class SearchPopup:
    """The command-bar style search popup with chat-over-files mode."""

    def __init__(
        self,
        root: tk.Tk,
        on_search: Callable[[str], dict[str, Any]],
        on_chat: Callable[[str], dict[str, Any]] | None = None,
        on_open: Callable[[str], None] | None = None,
        on_reveal: Callable[[str], None] | None = None,
        on_settings: Callable[[], None] | None = None,
        on_delete: Callable[[str], None] | None = None,
        on_undo: Callable[[], None] | None = None,
        config: SearchPopupConfig | None = None,
    ):
        self.root = root
        self._on_search = on_search
        self._on_chat = on_chat
        self._on_open = on_open or (lambda p: None)
        self._on_reveal_callback = on_reveal or (lambda p: None)
        self._on_settings_callback = on_settings
        self._on_delete_callback = on_delete
        self._on_undo_callback = on_undo
        self.config = config or SearchPopupConfig()
        self.window: tk.Toplevel | None = None
        self._query: tk.Entry | None = None
        self._query_var: tk.StringVar | None = None
        self._list: HoverList | None = None
        self._list_frame: tk.Frame | None = None
        self._placeholder: str = self.config.placeholder
        self._chat_placeholder: str = self.config.chat_placeholder
        self._placeholder_active: bool = True
        self._chat_mode: bool = False
        self._mode_icon: tk.Label | None = None
        self._mode_toggle_btn: tk.Label | None = None
        self._chat_answer: str = ""
        self._chat_results: list[dict[str, Any]] = []
        self._footer_frame: tk.Frame | None = None
        self._sidebar_frame: tk.Frame | None = None
        self._sidebar_surfaced: tk.Frame | None = None
        self._sidebar_graph: tk.Frame | None = None
        self._sidebar_clusters: tk.Frame | None = None
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
        try:
            place_at_cursor(win, self.config.width, self.config.height)
        except Exception:
            win.geometry(f"{self.config.width}x{self.config.height}+100+100")
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
    # Mode toggle
    # ------------------------------------------------------------------

    def _toggle_chat_mode(self) -> None:
        self._chat_mode = not self._chat_mode
        self._update_mode_ui()
        self._rebuild_footer()
        if self._query_var is not None and self._query is not None:
            self._query_var.set("")
            if self._chat_mode:
                self._query_var.set(self._chat_placeholder)
                self._query.configure(foreground=COLORS.fg.tertiary)
            else:
                self._query_var.set(self._placeholder)
                self._query.configure(foreground=COLORS.fg.tertiary)
            self._placeholder_active = True
        self._show_idle_state()

    def _update_mode_ui(self) -> None:
        assert self._mode_icon is not None and self._mode_toggle_btn is not None
        try:
            if self._chat_mode:
                icon = get_icon("chat", size=ICON_SIZE.sm, color=COLORS.accent.DEFAULT, master=self._mode_toggle_btn)
                self._mode_icon.configure(image=icon)
                self._mode_icon.image = icon  # type: ignore[attr-defined]
                self._mode_toggle_btn.configure(bg=COLORS.bg.selected)
            else:
                icon = get_icon("search", size=ICON_SIZE.sm, color=COLORS.fg.secondary, master=self._mode_toggle_btn)
                self._mode_icon.configure(image=icon)
                self._mode_icon.image = icon  # type: ignore[attr-defined]
                self._mode_toggle_btn.configure(bg=COLORS.bg.panel)
        except tk.TclError:
            pass

    # ------------------------------------------------------------------
    # Settings shortcut
    # ------------------------------------------------------------------

    def _rebuild_footer(self) -> None:
        """Rebuild the footer hints to reflect the current mode."""
        if self._footer_frame is None:
            return
        for w in list(self._footer_frame.winfo_children()):
            w.destroy()
        hints = [
            ("\u2191\u2193", "navigate"),
            ("\u21b5", "ask" if self._chat_mode else "open"),
        ]
        if not self._chat_mode:
            hints.append(("\u2318\u21b5", "reveal"))
        hints += [
            ("\u2318,", "settings"),
            ("esc", "close"),
        ]
        FooterHints(self._footer_frame, hints).pack(fill="x")

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
        win.configure(bg=COLORS.bg.canvas)
        strip_window_chrome(win, hide_titlebar=True)
        win.minsize(self.config.width - 80, 200)
        win.bind("<Escape>", lambda _e: self.hide())
        win.bind("<Control-comma>", lambda _e: self._open_settings())

        outer = tk.Frame(win, bg=COLORS.bg.canvas, bd=0, highlightthickness=0)
        outer.pack(fill="both", expand=True)
        body = tk.Frame(outer, bg=COLORS.bg.canvas, bd=0, highlightthickness=0)
        body.pack(fill="both", expand=True, padx=4, pady=4)

        # --- Horizontal layout: main area (right) + sidebar (left)
        content_row = tk.Frame(body, bg=COLORS.bg.canvas)
        content_row.pack(fill="both", expand=True)

        # --- Sidebar (left column with 3 panels)
        self._build_sidebar(content_row)

        # Spacer between sidebar and main card
        tk.Frame(content_row, bg=COLORS.bg.canvas, width=SPACING.lg).pack(side="left", fill="y")

        # --- Main column (command bar + results + footer) inside orange glowing card
        self.main_card = RoundedCard(
            content_row,
            bg=COLORS.bg.panel,
            outline=COLORS.accent.DEFAULT,
            width=2,
            radius=16,
        )
        self.main_card.pack(side="left", fill="both", expand=True)
        main_col = self.main_card.inner_frame

        # --- Command bar
        self._build_command_bar(main_col).pack(fill="x", padx=SPACING.lg, pady=(SPACING.lg, SPACING.sm))

        # --- Divider
        tk.Frame(main_col, bg=COLORS.border.subtle, height=1).pack(fill="x")

        # --- Results
        self._list_frame = tk.Frame(main_col, bg=COLORS.bg.panel)
        self._list_frame.pack(fill="both", expand=True, padx=SPACING.md, pady=SPACING.sm)
        self._list = HoverList(
            self._list_frame,
            on_activate=self._on_activate,
            on_reveal=self._on_reveal,
        )
        self._list.build().pack(fill="both", expand=True)

        # --- Footer (stored so it can be rebuilt on mode toggle)
        tk.Frame(main_col, bg=COLORS.border.subtle, height=1).pack(fill="x")
        self._footer_frame = tk.Frame(main_col)
        self._rebuild_footer()
        self._footer_frame.pack(fill="x")

        return win

    def _build_sidebar(self, parent: tk.Misc) -> None:
        """Build the left sidebar with three panels."""
        self._sidebar_frame = tk.Frame(parent, bg=COLORS.bg.canvas, width=SIZE.sidebar_w)
        self._sidebar_frame.pack(side="left", fill="y")
        self._sidebar_frame.pack_propagate(False)

        sidebar_inner = tk.Frame(self._sidebar_frame, bg=COLORS.bg.canvas)
        sidebar_inner.pack(fill="both", expand=True)

        # --- Panel 1: Surfaced For You
        self.surfaced_card = RoundedCard(
            sidebar_inner,
            bg=COLORS.bg.panel,
            outline=COLORS.border.subtle,
            width=1,
            radius=12,
            left_accent=COLORS.accent.DEFAULT,
        )
        self.surfaced_card.pack(fill="x", pady=(0, SPACING.md))
        self._sidebar_surfaced = self._build_sidebar_panel(
            self.surfaced_card.inner_frame, "SURFACED FOR YOU", [],
        )
        self._sidebar_surfaced.pack(fill="both", expand=True)

        # --- Panel 2: Local Graph
        self.graph_card = RoundedCard(
            sidebar_inner,
            bg=COLORS.bg.panel,
            outline=COLORS.border.subtle,
            width=1,
            radius=12,
            left_accent=COLORS.accent.DEFAULT,
        )
        self.graph_card.pack(fill="x", pady=(0, SPACING.md))
        self._sidebar_graph = self._build_sidebar_panel(
            self.graph_card.inner_frame, "LOCAL GRAPH", [],
        )
        self._sidebar_graph.pack(fill="both", expand=True)
        self._build_local_graph_viz(self._sidebar_graph)

        # --- Panel 3: Clusters
        self.clusters_card = RoundedCard(
            sidebar_inner,
            bg=COLORS.bg.panel,
            outline=COLORS.border.subtle,
            width=1,
            radius=12,
        )
        self.clusters_card.pack(fill="x")
        self._sidebar_clusters = self._build_sidebar_panel(
            self.clusters_card.inner_frame, "CLUSTERS", [],
        )
        self._sidebar_clusters.pack(fill="both", expand=True)
        self._build_clusters_grid(self._sidebar_clusters)

    def _build_local_graph_viz(self, parent: tk.Frame) -> None:
        """Draw a beautiful connected network node graph in the Local Graph panel."""
        canvas = tk.Canvas(parent, height=90, bg=COLORS.bg.panel, bd=0, highlightthickness=0)
        canvas.pack(fill="x", expand=True, pady=SPACING.xs)
        
        # Center node: (90, 45)
        center = (90, 45)
        # Surrounding nodes coordinates
        nodes = [
            (45, 30), (60, 20), (105, 20), (135, 35),
            (125, 65), (95, 75), (55, 70), (35, 50)
        ]
        
        # Connect nodes with lines
        for nx, ny in nodes:
            canvas.create_line(center[0], center[1], nx, ny, fill="#f97316", width=1.5)
            
        # Draw some cross-connections
        canvas.create_line(nodes[0][0], nodes[0][1], nodes[1][0], nodes[1][1], fill="#f97316", width=1)
        canvas.create_line(nodes[2][0], nodes[2][1], nodes[3][0], nodes[3][1], fill="#f97316", width=1.5)
        canvas.create_line(nodes[4][0], nodes[4][1], nodes[5][0], nodes[5][1], fill="#f97316", width=1)
        canvas.create_line(nodes[6][0], nodes[6][1], nodes[7][0], nodes[7][1], fill="#f97316", width=1)
        
        # Draw center node (larger)
        cr = 6
        canvas.create_oval(center[0]-cr, center[1]-cr, center[0]+cr, center[1]+cr, fill="#f97316", outline="")
        
        # Draw surrounding nodes (smaller)
        sr = 3
        for nx, ny in nodes:
            canvas.create_oval(nx-sr, ny-sr, nx+sr, ny+sr, fill="#f97316", outline="")

        # Draw labels below graph
        labels_frame = tk.Frame(parent, bg=COLORS.bg.panel)
        labels_frame.pack(fill="x", padx=SPACING.xs)
        tk.Label(
            labels_frame, text="Local Graph",
            font=TYPOGRAPHY.caption.font(),
            fg=COLORS.fg.primary,
            bg=COLORS.bg.panel,
        ).pack(anchor="w")
        tk.Label(
            labels_frame, text="Nodes · Edges · Clusters",
            font=TYPOGRAPHY.micro.font(),
            fg=COLORS.fg.secondary,
            bg=COLORS.bg.panel,
        ).pack(anchor="w")

    def _build_clusters_grid(self, parent: tk.Frame) -> None:
        """Render a 2x4 grid of rounded icon buttons."""
        _RADIUS = 6

        def draw_btn(c: tk.Canvas, color: str, icon_n: str, color_icon: str) -> None:
            r = _RADIUS
            c.create_arc(0, 0, 2*r, 2*r, start=90, extent=90, fill=color, outline="")
            c.create_arc(32-2*r, 0, 32, 2*r, start=0, extent=90, fill=color, outline="")
            c.create_arc(32-2*r, 32-2*r, 32, 32, start=270, extent=90, fill=color, outline="")
            c.create_arc(0, 32-2*r, 2*r, 32, start=180, extent=90, fill=color, outline="")
            c.create_rectangle(r, 0, 32-r, 32, fill=color, outline="")
            c.create_rectangle(0, r, 32, 32-r, fill=color, outline="")
            img = get_icon(icon_n, size=16, color=color_icon, master=c)
            c.create_image(16, 16, image=img)
            c.image = img  # type: ignore[attr-defined]

        def make_hover(canvas: tk.Canvas, icon_n: str) -> None:
            canvas.bind(
                "<Enter>",
                lambda _e, c=canvas, n=icon_n: (
                    c.delete("all"),
                    draw_btn(c, COLORS.bg.hover, n, COLORS.accent.hover),
                ),
            )
            canvas.bind(
                "<Leave>",
                lambda _e, c=canvas, n=icon_n: (
                    c.delete("all"),
                    draw_btn(c, COLORS.bg.elevated, n, COLORS.accent.DEFAULT),
                ),
            )

        grid_frame = tk.Frame(parent, bg=COLORS.bg.panel)
        grid_frame.pack(fill="x", pady=SPACING.xs)

        cluster_icons = [
            "logo", "chat", "folder", "globe",
            "database", "gear", "info", "warning",
        ]

        for idx, icon_name in enumerate(cluster_icons):
            row_idx = idx // 4
            col_idx = idx % 4
            btn_canvas = tk.Canvas(
                grid_frame, width=32, height=32,
                bg=COLORS.bg.panel, bd=0, highlightthickness=0, cursor="hand2",
            )
            btn_canvas.grid(row=row_idx, column=col_idx, padx=SPACING.xxs, pady=SPACING.xxs)
            draw_btn(btn_canvas, COLORS.bg.elevated, icon_name, COLORS.accent.DEFAULT)
            make_hover(btn_canvas, icon_name)

    def _build_sidebar_panel(
        self, parent: tk.Misc, title: str, items: list[str],
    ) -> tk.Frame:
        """Build a single sidebar panel with a header and item list."""
        panel = tk.Frame(parent, bg=COLORS.bg.panel)

        # Header
        header = tk.Frame(panel, bg=COLORS.bg.panel)
        header.pack(fill="x", padx=SPACING.xs, pady=(0, SPACING.xs))
        ttk.Label(
            header, text=title.upper(),
            font=TYPOGRAPHY.caption.font(),
            foreground=COLORS.accent.DEFAULT,
            background=COLORS.bg.panel,
        ).pack(anchor="w", padx=SPACING.xs, pady=SPACING.xs)

        return panel

    def _update_sidebar(
        self,
        surfaced: list[str] | None = None,
        graph: list[str] | None = None,
        clusters: list[str] | None = None,
    ) -> None:
        """Update sidebar panels with new data."""
        if self._sidebar_surfaced is not None:
            self._rebuild_sidebar_panel(
                self._sidebar_surfaced, "SURFACED FOR YOU",
                surfaced or [],
            )

    def _rebuild_sidebar_panel(
        self, panel: tk.Frame, title: str, items: list[str],
    ) -> None:
        """Rebuild a sidebar panel's content while preserving the header."""
        children = list(panel.winfo_children())
        for child in children[1:]:
            child.destroy()

        items_frame = tk.Frame(panel, bg=COLORS.bg.panel)
        items_frame.pack(fill="both", expand=True)

        if not items:
            default_items = ["Suggested Item", "Project_Brofit"]
            for idx, item in enumerate(default_items):
                row = tk.Frame(items_frame, bg=COLORS.bg.panel)
                row.pack(fill="x", pady=SPACING.xxs)
                
                icon_n = "arrow-right" if idx == 0 else "document"
                icon_img = get_icon(icon_n, size=14, color=COLORS.accent.DEFAULT, master=row)
                icon_lbl = tk.Label(row, image=icon_img, bg=COLORS.bg.panel)
                icon_lbl.image = icon_img
                icon_lbl.pack(side="left", padx=(SPACING.xs, SPACING.sm))
                
                text_frame = tk.Frame(row, bg=COLORS.bg.panel)
                text_frame.pack(side="left", fill="both", expand=True)
                
                ttk.Label(
                    text_frame, text=item,
                    font=TYPOGRAPHY.body.font(),
                    foreground=COLORS.fg.primary,
                    background=COLORS.bg.panel,
                ).pack(anchor="w")
                
                desc = "Considered suggestion far..." if idx == 0 else "Make suggested connection..."
                ttk.Label(
                    text_frame, text=desc,
                    font=TYPOGRAPHY.micro.font(),
                    foreground=COLORS.fg.secondary,
                    background=COLORS.bg.panel,
                ).pack(anchor="w")
        else:
            for item in items[:2]:
                row = tk.Frame(items_frame, bg=COLORS.bg.panel)
                row.pack(fill="x", pady=SPACING.xxs)
                
                icon_img = get_icon("document", size=14, color=COLORS.accent.DEFAULT, master=row)
                icon_lbl = tk.Label(row, image=icon_img, bg=COLORS.bg.panel)
                icon_lbl.image = icon_img
                icon_lbl.pack(side="left", padx=(SPACING.xs, SPACING.sm))
                
                text_frame = tk.Frame(row, bg=COLORS.bg.panel)
                text_frame.pack(side="left", fill="both", expand=True)
                
                ttk.Label(
                    text_frame, text=str(item)[:20],
                    font=TYPOGRAPHY.body.font(),
                    foreground=COLORS.fg.primary,
                    background=COLORS.bg.panel,
                ).pack(anchor="w")
                
                ttk.Label(
                    text_frame, text="Suggested file...",
                    font=TYPOGRAPHY.micro.font(),
                    foreground=COLORS.fg.secondary,
                    background=COLORS.bg.panel,
                ).pack(anchor="w")

    def _build_command_bar(self, parent: tk.Misc) -> tk.Frame:
        bar = tk.Frame(parent, bg=COLORS.bg.panel)

        # Mode toggle button (left side, before the query)
        self._mode_toggle_btn = tk.Label(
            bar,
            bg=COLORS.bg.panel,
            cursor="hand2",
            padx=4, pady=2,
        )
        self._mode_toggle_btn.pack(side="left", padx=(0, SPACING.xs))
        # Default search icon
        search_icon = get_icon("search", size=ICON_SIZE.sm, color=COLORS.fg.secondary, master=self._mode_toggle_btn)
        self._mode_icon = tk.Label(
            self._mode_toggle_btn, image=search_icon,
            bg=COLORS.bg.panel, cursor="hand2",
        )
        self._mode_icon.image = search_icon  # type: ignore[attr-defined]
        self._mode_icon.pack()
        self._mode_toggle_btn.bind("<Button-1>", lambda _e: self._toggle_chat_mode())
        self._mode_toggle_btn.bind("<Enter>", lambda _e: self._mode_toggle_btn.configure(bg=COLORS.bg.hover) if not self._chat_mode else None)
        self._mode_toggle_btn.bind("<Leave>", lambda _e: self._mode_toggle_btn.configure(bg=COLORS.bg.panel) if not self._chat_mode else None)

        self._query_var = tk.StringVar()
        self._query = tk.Entry(
            bar,
            textvariable=self._query_var,
            bg=COLORS.bg.input, fg=COLORS.fg.primary,
            insertbackground=COLORS.accent.DEFAULT,
            relief="flat", highlightthickness=1,
            highlightbackground=COLORS.border.DEFAULT,
            highlightcolor=COLORS.accent.glow_border,
            bd=0,
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
        """Clear the query and show idle state for current mode."""
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
            placeholder = self._chat_placeholder if self._chat_mode else self._placeholder
            self._query_var.set(placeholder)
            self._query.configure(foreground=COLORS.fg.tertiary)
            self._placeholder_active = True

    # ------------------------------------------------------------------
    # Key handling
    # ------------------------------------------------------------------

    def _on_keyrelease(self, event: tk.Event) -> None:
        if event.keysym in (
            "Up", "Down", "Left", "Right", "Home", "End",
            "Return", "Escape", "Shift_L", "Shift_R", "Control_L", "Control_R",
        ):
            return
        if self._chat_mode:
            return  # No live search in chat mode
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
        if self._chat_mode:
            assert self._query_var is not None
            q = self._query_var.get()
            if q and not self._placeholder_active:
                self._kick_chat(q)
            return "break"
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

    def _kick_chat(self, question: str) -> None:
        """Send a chat question in a background thread."""
        if self._on_chat is None:
            return
        self._search_generation += 1
        generation = self._search_generation
        assert self._list is not None
        self._list.show_shimmer()

        def worker() -> None:
            try:
                payload = self._on_chat(question)
            except Exception as exc:
                payload = {"status": "error", "answer": "", "results": [], "message": str(exc)}
            if not isinstance(payload, dict):
                payload = {"status": "error", "answer": "", "results": [], "message": "Invalid response"}
            self._results_queue.put((generation, payload))

        threading.Thread(target=worker, daemon=True, name="golem-chat").start()

    def _pump_results(self) -> None:
        try:
            while True:
                generation, payload = self._results_queue.get_nowait()
                if generation >= self._latest_rendered_generation:
                    self._latest_rendered_generation = generation
                    if self._chat_mode and isinstance(payload, dict) and "answer" in payload:
                        self._show_chat_response(payload)
                    else:
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
            self._list.select_first()
        # Update sidebar with search result data
        self._update_sidebar_from_results(self.results)

    def _update_sidebar_from_results(self, results: list[dict[str, Any]]) -> None:
        """Update the sidebar Surfaced For You panel with the top search results."""
        if self._sidebar_surfaced is None:
            return
        names = [
            str(r.get("clean_filename") or r.get("original_filename") or "")
            for r in results[:2]
            if r.get("clean_filename") or r.get("original_filename")
        ]
        self._rebuild_sidebar_panel(self._sidebar_surfaced, "SURFACED FOR YOU", names)

    def _show_chat_response(self, payload: dict[str, Any]) -> None:
        """Display a chat answer in the list area."""
        assert self._list is not None
        answer = str(payload.get("answer", "") or "")
        results = list(payload.get("results", []))
        self._chat_answer = answer
        self._chat_results = results
        status = payload.get("status", "ok")
        message = str(payload.get("message", "") or "")

        if status == "error" or not answer:
            self._list.show_empty("alert", "No answer", message or "The AI could not generate a response.")
            return

        # Show answer as a set of rows
        rows: list[_RowSpec] = []
        # First row: the answer (multi-line, just a primary line)
        answer_preview = answer[:120] + ("\u2026" if len(answer) > 120 else "")
        rows.append(_RowSpec(
            primary="Answer",
            secondary=answer_preview,
            payload="",
        ))
        # Supporting files
        for r in results[:4]:
            name = r.get("clean_filename") or r.get("original_filename") or "(unnamed)"
            summary = r.get("summary", "") or ""
            category = r.get("category", "") or ""
            badge = None
            if category:
                color = getattr(COLORS.category, category.lower(), COLORS.category.other)
                badge = (category, color)
            rows.append(_RowSpec(
                primary=name,
                secondary=summary,
                badge=badge,
                payload=r.get("current_path") or r.get("original_path") or "",
            ))
        self._list.set_rows(rows)
        self._list.select_first()

    def _to_row(self, r: dict[str, Any]) -> _RowSpec:
        primary = r.get("clean_filename") or r.get("original_filename") or "(unnamed)"
        secondary = text_excerpt(str(r.get("chunk_text") or r.get("summary") or ""), 140)
        category = r.get("category") or ""
        confidence = r.get("confidence")
        match_type = str(r.get("match_type") or "")
        tertiary = ""
        if match_type:
            tertiary = match_type
        if confidence is not None and confidence != "":
            try:
                pct = f"{float(confidence) * 100:.0f}%"
                tertiary = f"{tertiary} · {pct}" if tertiary else pct
            except (TypeError, ValueError):
                pass
        badge = None
        if category:
            color = getattr(COLORS.category, category.lower(), COLORS.category.other)
            badge = (category, color)
        # Why-matched pill from match_type
        match_pill: tuple[str, str] | None = None
        match_type = r.get("match_type", "")
        if match_type:
            match_pill_map = {
                "keyword": ("keyword", COLORS.match_pill.keyword),
                "semantic": ("semantic", COLORS.match_pill.semantic),
                "both": ("both", COLORS.match_pill.both),
                "entity": ("entity", COLORS.match_pill.entity),
                "temporal": ("temporal", COLORS.match_pill.temporal),
            }
            match_pill = match_pill_map.get(str(match_type).lower())
        # Build related badges from graph context
        related_badges: list[tuple[str, str]] = []
        related = r.get("related", [])
        if isinstance(related, list):
            for item in related[:6]:
                rlabel = str(item.get("label", "") or "")
                rtype = str(item.get("type", "") or "")
                if not rlabel:
                    continue
                type_colors = {
                    "tag": COLORS.accent.muted,
                    "project": COLORS.fg.tertiary,
                    "related_file": COLORS.accent.dim,
                }
                rcolor = type_colors.get(rtype, COLORS.fg.tertiary)
                related_badges.append((rlabel, rcolor))
        return _RowSpec(
            primary=str(primary),
            secondary=str(secondary),
            tertiary=tertiary,
            badge=badge,
            match_pill=match_pill,
            related_badges=related_badges,
            payload=r.get("current_path") or r.get("original_path") or "",
        )

    def _show_idle_state(self) -> None:
        assert self._list is not None
        if not self.results and not self._chat_answer:
            if self._chat_mode:
                self._list.show_empty(
                    "chat",
                    "Ask a question about your files",
                    "Type a natural language question and press Enter. "
                    "GOLEM will search the index and answer using AI.",
                )
            else:
                self._list.show_empty(
                    "search",
                    "Search your vault",
                    "Drop a file into the watched folder to start. Press Esc to close.",
                )

    def set_status(self, message: str) -> None:
        if not message or self._query_var is None or self._query is None:
            return
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
