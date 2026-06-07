"""GOLEM UI Demo — renders the search popup with demo data and takes a screenshot.

Run: python demo_ui.py
Output: golem_ui_screenshot.png (saved to project root)

This script:
1. Creates a hidden Tk root
2. Builds the SearchPopup with the spec's DEMO_RESULTS hardcoded
3. Opens the popup, populates demo data, selects the first result
4. Takes a screenshot with PIL
5. Saves and exits
"""
from __future__ import annotations

import os
import sys
import time

# Ensure the project root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import tkinter as tk

from PIL import ImageGrab

from golem.ui_theme import COLORS, Motion, apply_theme
from golem.ui_window import apply_dpi_scaling

# ── DEMO_RESULTS from the spec ─────────────────────────────────────

DEMO_RESULTS = [
    {
        "group": "FILES",
        "file_name": "Pricing Strategy Q3 2024.pdf",
        "file_type": "pdf",
        "file_path": "~/Documents/Business/Pricing Strategy Q3 2024.pdf",
        "snippet": "Value metric pricing outperforms seat-based by 3x in expansion revenue. The key insight is finding what your customer actually values…",
        "match_type": "both",
        "matched_terms": ["pricing", "strategy"],
        "modified_at": "3 days ago",
    },
    {
        "group": "VIDEOS",
        "file_name": "How to Price SaaS — Patrick Campbell",
        "file_type": "video",
        "file_path": "YouTube · ingested 12 days ago",
        "snippet": "Timestamp 14:32 — pricing outperforms seat-based by 3x in expansion revenue…",
        "match_type": "semantic",
        "matched_terms": ["pricing"],
        "modified_at": "12 days ago",
    },
    {
        "group": "NOTES",
        "file_name": "Meeting with Tariq — March notes.md",
        "file_type": "md",
        "file_path": "~/Notes/Meetings/Meeting with Tariq — March notes.md",
        "snippet": "Tariq mentioned the value metric framework again. He thinks our current per-seat model is leaving money on the table…",
        "match_type": "entity",
        "matched_terms": ["pricing", "model"],
        "modified_at": "2 weeks ago",
    },
    {
        "group": "FILES",
        "file_name": "Competitor Analysis Jan 2024.xlsx",
        "file_type": "xlsx",
        "file_path": "~/Documents/Research/Competitor Analysis Jan 2024.xlsx",
        "snippet": "Pricing tier breakdown — Linear, Notion, Figma. Section incomplete…",
        "match_type": "keyword",
        "matched_terms": ["pricing"],
        "modified_at": "5 months ago",
    },
    {
        "group": "AUDIO",
        "file_name": "Voice memo — freemium thoughts.m4a",
        "file_type": "audio",
        "file_path": "~/Voice Memos/Voice memo — freemium thoughts.m4a",
        "snippet": "…the problem with freemium is you train users to expect value for free, so when you introduce pricing tiers…",
        "match_type": "semantic",
        "matched_terms": ["pricing", "freemium"],
        "modified_at": "3 weeks ago",
    },
]


def demo_search_handler(query: str, top_k: int = 8) -> list[dict]:
    """Return hardcoded demo results as if the backend searched."""
    return DEMO_RESULTS[:top_k]


def main():
    print("Building GOLEM UI demo...")

    # Create root (hidden)
    root = tk.Tk()
    root.withdraw()
    apply_dpi_scaling(root)
    apply_theme(root)

    # Clear stale icon cache
    from golem.ui_icons import invalidate_cache
    try:
        invalidate_cache()
    except Exception:
        pass

    # Set reduced motion for reliable screenshots
    import golem.ui_theme as _t
    _t.MOTION = Motion(reduced_motion=True)

    # Build the search popup with demo search handler
    from golem.ui_search import SearchPopup, SearchPopupConfig

    config = SearchPopupConfig(
        width=640,
        height=560,
        max_visible_results=8,
        top_k=8,
    )

    popup = SearchPopup(
        root,
        on_search=demo_search_handler,
        on_open=lambda p: print(f"[demo] Open: {p}"),
        on_reveal=lambda p: print(f"[demo] Reveal: {p}"),
        config=config,
    )

    # Open the popup
    print("Opening search popup...")
    popup.open()

    # Wait for window to appear and render
    root.update_idletasks()
    root.update()
    time.sleep(0.3)

    # Simulate typing a query to trigger demo search results
    if popup._query is not None and popup._query_var is not None:
        # Focus the search box
        popup._query.focus_set()
        root.update()

        # Type a query to trigger search
        popup._on_focus_in(None)
        popup._query_var.set("pricing strategy")
        popup._query.configure(foreground=COLORS.fg.primary)
        popup._placeholder_active = False
        root.update()

        # Manually trigger search (bypass debounce for demo)
        raw_results = demo_search_handler("pricing strategy", 8)
        popup.results = popup._dicts_to_results(raw_results)
        popup._selected_idx = 0  # Select first result
        popup._scroll_offset = 0
        popup._render_results()
        root.update_idletasks()
        root.update()
        time.sleep(0.2)

    # Make sure the window is visible and positioned
    if popup.window:
        popup.window.deiconify()
        popup.window.lift()
        popup.window.focus_set()
        popup.window.update_idletasks()

        # Position centered on screen for clean screenshot
        sw = root.winfo_screenwidth()
        sh = root.winfo_screenheight()
        x = (sw - 640) // 2
        y = (sh - 560) // 3  # Upper third looks better
        popup.window.geometry(f"640x560+{x}+{y}")
        popup.window.update_idletasks()
        root.update()
        time.sleep(0.3)

        # Take screenshot
        print(f"Taking screenshot at {x},{y} (640x560)...")
        screenshot = ImageGrab.grab(bbox=(x, y, x + 640, y + 560))

        # Save
        output_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "golem_ui_screenshot.png")
        screenshot.save(output_path)
        print(f"Screenshot saved to: {output_path}")
        print(f"Image size: {screenshot.size}")

        # Also save a second screenshot with hover on second item
        popup._selected_idx = 1
        popup._render_results()
        root.update_idletasks()
        root.update()
        time.sleep(0.2)

        screenshot2 = ImageGrab.grab(bbox=(x, y, x + 640, y + 560))
        output_path2 = os.path.join(os.path.dirname(os.path.abspath(__file__)), "golem_ui_screenshot_selected.png")
        screenshot2.save(output_path2)
        print(f"Selected-state screenshot saved to: {output_path2}")

    # Clean up
    popup.hide()
    root.update()
    time.sleep(0.2)
    root.destroy()

    print("\n✅ Demo complete! Open golem_ui_screenshot.png to see the result.")
    print("   golem_ui_screenshot_selected.png shows the second item selected.")


if __name__ == "__main__":
    main()
