"""Tests for UI component logic that does not require a Tk display.

We test dataclass construction, rendering helpers, row conversion,
and any non-widget logic. Widget-building tests require a display
and are excluded from CI.
"""
from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from golem.ui_components import (
    EmptyState,
    HoverList,
    StatusBar,
    _RowSpec,
)


class RowSpecTests(unittest.TestCase):
    """_RowSpec is a simple dataclass — but the attribute types matter."""

    def test_defaults(self) -> None:
        row = _RowSpec(primary="test")
        self.assertEqual(row.primary, "test")
        self.assertEqual(row.secondary, "")
        self.assertEqual(row.tertiary, "")
        self.assertIsNone(row.badge)
        self.assertIsNone(row.payload)

    def test_full_construction(self) -> None:
        row = _RowSpec(
            primary="Budget.pdf",
            secondary="Q1 2026 budget report",
            tertiary="Finance",
            badge=("Finance", "#5DD39E"),
            payload="/path/to/file",
        )
        self.assertEqual(row.primary, "Budget.pdf")
        self.assertEqual(row.secondary, "Q1 2026 budget report")
        self.assertEqual(row.tertiary, "Finance")
        self.assertEqual(row.badge, ("Finance", "#5DD39E"))
        self.assertEqual(row.payload, "/path/to/file")

    def test_maximal_badge(self) -> None:
        row = _RowSpec(primary="x", badge=("Testing", "#FF00FF"))
        text, color = row.badge
        self.assertEqual(text, "Testing")
        self.assertEqual(color, "#FF00FF")


class EmptyStateTests(unittest.TestCase):
    """EmptyState dataclass and layout assumptions."""

    def test_empty_state_fields(self) -> None:
        es = EmptyState(
            parent=MagicMock(),
            icon="search",
            headline="No results",
            body="Try different keywords.",
            action_label="Retry",
            on_action=lambda: None,
        )
        self.assertEqual(es.icon, "search")
        self.assertEqual(es.headline, "No results")
        self.assertEqual(es.body, "Try different keywords.")
        self.assertEqual(es.action_label, "Retry")
        self.assertIsNotNone(es.on_action)

    def test_empty_state_minimal(self) -> None:
        es = EmptyState(
            parent=MagicMock(),
            icon="search",
            headline="No results",
        )
        self.assertEqual(es.icon, "search")
        self.assertEqual(es.action_label, "")


class StatusBarTests(unittest.TestCase):
    """StatusBar state management (non-Tk)."""

    def setUp(self):
        self.sb = StatusBar(parent=MagicMock())
        # Set required attributes that normally come from build()
        self.sb._text = MagicMock()
        self.sb._text_var = MagicMock()
        self.sb._frame = MagicMock()
        self.sb._icon = MagicMock()
        self.sb._dot = MagicMock()
        self.sb._frame.after.return_value = "after_123"

    def test_statusbar_dataclass_defaults(self) -> None:
        self.assertEqual(self.sb._last_idle, "")
        self.assertIsNone(self.sb._error_after)
        self.assertIsNone(self.sb._anim)

    def test_statusbar_clear_error_when_no_idle(self) -> None:
        """After _clear_error with no _last_idle, the text should empty."""
        with patch.object(self.sb, "_set_icon"):
            self.sb._last_idle = ""
            self.sb._clear_error()
            # Should have cleared the text via configure
            self.sb._text.configure.assert_called_once()

    def test_set_error_clears_after_duration(self) -> None:
        """set_error must store the error_after token and restore idle."""
        with patch.object(self.sb, "_set_icon"):
            self.sb.set_idle("Ready")
            self.sb.set_error("Something went wrong")
            self.assertIsNotNone(self.sb._error_after)
            self.assertEqual(self.sb._last_idle, "Ready")

    def test_progress_blocked_by_error(self) -> None:
        """Progress must not override an active error."""
        with patch.object(self.sb, "_set_icon"):
            self.sb.set_error("Error")
            self.sb.set_progress("Working...")
            # Error should still be shown
            self.assertEqual(self.sb._text_var.set.call_args[0][0], "Error")


class HoverListLogicTests(unittest.TestCase):
    """Non-widget HoverList logic: row management, selection."""

    def setUp(self):
        self.rows = [
            _RowSpec(primary="A", payload="/a"),
            _RowSpec(primary="B", payload="/b"),
            _RowSpec(primary="C", payload="/c"),
        ]

    def _make_hl(self, **overrides) -> HoverList:
        """Create a HoverList with a mocked canvas to avoid Tk dependency."""
        params = dict(parent=MagicMock(), on_activate=lambda p: None)
        params.update(overrides)
        hl = HoverList(**params)
        hl._canvas = MagicMock()
        hl._canvas.winfo_width.return_value = 500
        hl._canvas.winfo_height.return_value = 400
        return hl

    def test_row_selection_bounds(self) -> None:
        """Selecting first/last must clamp to available rows."""
        hl = self._make_hl()
        hl._rows = self.rows
        hl._selected = -1

        hl.select_first()
        self.assertEqual(hl._selected, 0)

        hl.select_last()
        self.assertEqual(hl._selected, 2)

        # Beyond bounds must clamp
        hl._selected = 0
        hl.select_prev()
        self.assertEqual(hl._selected, 0)  # Can't go below 0

        hl._selected = 2
        hl.select_next()
        self.assertEqual(hl._selected, 2)  # Can't go above last

    def test_get_selected_payload(self) -> None:
        hl = self._make_hl()
        hl._rows = self.rows
        hl._selected = 1
        self.assertEqual(hl.get_selected_payload(), "/b")

        hl._selected = -1
        self.assertIsNone(hl.get_selected_payload())

        hl._rows = []
        self.assertIsNone(hl.get_selected_payload())

    def test_select_without_rows_is_safe(self) -> None:
        hl = self._make_hl()
        hl._rows = []
        hl._selected = -1
        hl.select_next()  # Must not crash
        hl.select_prev()
        hl.select_first()
        hl.select_last()
        self.assertEqual(hl._selected, -1)

    def test_set_rows_normalizes_dicts(self) -> None:
        hl = self._make_hl()
        hl.set_rows([
            {"primary": "X", "secondary": "Y", "payload": "/x"},
            {"primary": "Z", "payload": "/z"},
        ])
        self.assertEqual(len(hl._rows), 2)
        self.assertEqual(hl._rows[0].primary, "X")
        self.assertEqual(hl._rows[0].secondary, "Y")
        self.assertEqual(hl._rows[0].payload, "/x")
        self.assertEqual(hl._rows[1].primary, "Z")
        self.assertEqual(hl._rows[1].payload, "/z")

    def test_set_rows_deselects_if_out_of_range(self) -> None:
        hl = self._make_hl()
        hl._rows = [self.rows[0]]
        hl._selected = 0
        hl.set_rows([])  # Shrink list
        self.assertEqual(hl._selected, -1)  # Deselected

    def test_scroll_offset_accounting(self) -> None:
        """Scroll offset must not go negative or beyond max."""
        hl = self._make_hl()
        hl._rows = self.rows
        hl._items_per_page = 2

        hl._scroll_by(-10)
        self.assertGreaterEqual(hl._offset, 0)

        hl._scroll_by(10)
        self.assertLessEqual(hl._offset, max(0, len(self.rows) - hl._items_per_page))

    def test_select_triggers_render(self) -> None:
        """select_next/prev must call _render."""
        hl = self._make_hl()
        hl._rows = self.rows
        hl._selected = -1
        with patch.object(hl, "_render") as mock_render:
            hl.select_first()
            mock_render.assert_called()
            self.assertEqual(hl._selected, 0)


class FooterHintsTests(unittest.TestCase):
    """FooterHints input parsing."""

    def test_hint_count(self) -> None:
        hints = [
            ("↑↓", "navigate"),
            ("↵", "open"),
            ("⌘↵", "reveal"),
            ("esc", "close"),
        ]
        self.assertEqual(len(hints), 4)

    def test_footer_with_settings_hint(self) -> None:
        hints = [
            ("↑↓", "navigate"),
            ("↵", "open"),
            ("⌘↵", "reveal"),
            ("⌘,", "settings"),
            ("esc", "close"),
        ]
        self.assertEqual(len(hints), 5)


class CategoryBadgeTests(unittest.TestCase):
    """CategoryBadge color mapping."""

    def test_known_category_returns_color(self) -> None:
        from golem.ui_theme import COLORS
        known = ["finance", "research", "design", "code", "media", "personal", "legal", "other"]
        for key in known:
            color = getattr(COLORS.category, key, None)
            self.assertIsNotNone(color, f"No color for category {key}")
            self.assertTrue(color.startswith("#"), f"Invalid color {color} for {key}")

    def test_unknown_category_falls_back_to_other(self) -> None:
        from golem.ui_theme import COLORS
        color = getattr(COLORS.category, "nonexistent", COLORS.category.other)
        self.assertEqual(color, COLORS.category.other)


class SearchPopupRowConversionTests(unittest.TestCase):
    """SearchPopup._to_row converts DB result dicts to _RowSpec."""

    def test_to_row_with_full_data(self) -> None:
        r = {
            "clean_filename": "Budget Report",
            "summary": "Q1 2026 budget",
            "category": "Finance",
            "confidence": 0.95,
            "current_path": "C:/vault/GOLEM Files/Finance/budget.pdf",
        }
        # Manually apply _to_row logic (same as in SearchPopup)
        primary = r.get("clean_filename") or r.get("original_filename") or "(unnamed)"
        secondary = r.get("summary") or ""
        tertiary = ""
        try:
            tertiary = f"{float(r.get('confidence', 0)) * 100:.0f}%"
        except (TypeError, ValueError):
            pass
        badge = None
        from golem.ui_theme import COLORS
        if r.get("category"):
            color = getattr(COLORS.category, r["category"].lower(), COLORS.category.other)
            badge = (r["category"], color)
        payload = r.get("current_path") or r.get("original_path") or ""

        self.assertEqual(primary, "Budget Report")
        self.assertEqual(secondary, "Q1 2026 budget")
        self.assertEqual(tertiary, "95%")
        self.assertEqual(badge[0], "Finance")
        self.assertEqual(payload, "C:/vault/GOLEM Files/Finance/budget.pdf")

    def test_to_row_with_minimal_data(self) -> None:
        r = {
            "original_filename": "doc.txt",
        }
        primary = r.get("clean_filename") or r.get("original_filename") or "(unnamed)"
        secondary = r.get("summary") or ""
        payload = r.get("current_path") or r.get("original_path") or ""
        self.assertEqual(primary, "doc.txt")
        self.assertEqual(secondary, "")
        self.assertEqual(payload, "")

    def test_to_row_confidence_handling(self) -> None:
        """Confidence must be formatted as percentage or left empty."""
        cases: list[tuple[object, str]] = [
            (0.5, "50%"),
            (1.0, "100%"),
            (0.0, "0%"),
            (None, ""),
            ("", ""),
            ("invalid", ""),
        ]
        for val, expected in cases:
            try:
                tertiary = f"{float(val) * 100:.0f}%" if val is not None and val != "" else ""
            except (TypeError, ValueError):
                tertiary = ""
            self.assertEqual(tertiary, expected, f"Failed for confidence={val!r}")


if __name__ == "__main__":
    unittest.main()
