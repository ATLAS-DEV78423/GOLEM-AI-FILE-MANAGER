"""Top-level UI orchestrator. Replaces the old monolithic :mod:`golem.ui`.

The previous file mixed the search popup and the onboarding wizard
into a single ``DesktopApp`` class. The new orchestrator:

- holds the root Tk window (withdrawn, never shown)
- composes :class:`SearchPopup` and :class:`OnboardingWizard`
- surfaces a persistent :class:`StatusBar` at the bottom of the popup
- exposes the same ``run / show_onboarding / show_popup / set_status``
  API the rest of the app already calls

The legacy ``SearchPopup`` and ``OnboardingWizard`` classes are still
importable from this module for backward compatibility — they are the
new themed versions from :mod:`golem.ui_search` and
:mod:`golem.ui_onboarding`.
"""
from __future__ import annotations

import logging
import queue
import tkinter as tk
from collections.abc import Callable
from typing import Any

from .ui_components import StatusBar
from .ui_onboarding import OnboardingResult, OnboardingWizard
from .ui_search import SearchPopup, SearchPopupConfig
from .ui_theme import apply_theme
from .ui_window import apply_dpi_scaling, detect_reduced_motion

_LOG = logging.getLogger(__name__)


# Re-export the legacy names for backward compatibility.
__all__ = [
    "DesktopApp",
    "OnboardingWizard",
    "OnboardingResult",
    "SearchPopup",
    "SearchPopupConfig",
    "UIConfig",
    "set_status_silently",
]


# ---------------------------------------------------------------------------
# Backward-compat config
# ---------------------------------------------------------------------------


class UIConfig:
    """Compatibility shim for the old dataclass-based config.

    The new UI sizes itself from :class:`golem.ui_theme.SIZE`. This
    class is kept so existing imports of ``UIConfig`` don't break.
    """

    def __init__(self, title: str = "GOLEM", width: int = 420, height: int = 520):
        self.title = title
        self.width = width
        self.height = height


# ---------------------------------------------------------------------------
# DesktopApp orchestrator
# ---------------------------------------------------------------------------


class DesktopApp:
    """The application's UI orchestrator.

    Args:
        on_search:        Search worker. Called on a background thread.
        on_chat:          Chat-over-files worker. Called on a background thread.
        on_open:          Open a file (called on the UI thread).
        on_reveal:        Reveal a file in the OS file manager.
        on_save_config:   Onboarding completion callback. Receives
                          either a single :class:`OnboardingResult` or
                          the legacy 7-arg tuple.
    """

    def __init__(
        self,
        on_search: Callable[[str, int], list[dict[str, Any]]],
        on_open: Callable[[str], None],
        on_reveal: Callable[[str], None],
        on_save_config: Callable[..., None],
    ):
        self.root = tk.Tk()
        self.root.withdraw()
        # Apply DPI scaling & theme
        try:
            apply_dpi_scaling(self.root)
        except Exception:
            _LOG.exception("DPI scaling failed")
        try:
            apply_theme(self.root)
        except Exception:
            _LOG.exception("apply_theme failed")
        # Clear any stale icon cache (it would hold PhotoImages bound
        # to a previous Tk interpreter).
        try:
            from .ui_icons import invalidate_cache
            invalidate_cache()
        except Exception:
            pass
        # Try to detect reduced-motion preference
        try:
            import golem.ui_theme as _t

            from .ui_theme import Motion
            _t.MOTION = Motion(reduced_motion=detect_reduced_motion())
        except Exception:
            pass
        # Compose
        self.popup = SearchPopup(
            self.root,
            on_search=on_search,
            on_open=on_open,
            on_reveal=on_reveal,
        )
        self.onboarding = OnboardingWizard(self.root, on_save_config)
        self._search_handler = on_search
        self._search_results: queue.Queue[tuple[int, dict[str, Any]]] = queue.Queue()
        self._search_generation = 0
        self._latest_rendered_generation = 0
        # Persistent status bar (drawn inside the popup's footer area)
        self._status_bar = StatusBar(self.root)
        # Bridge: when the app calls set_status, the SearchPopup's
        # command bar hint text and the status bar's set_idle update.
        self._idle_message: str = ""
        # Pump for legacy search-results feed (kept for any old callers
        # that still push through _search_results).
        self.root.after(100, self._pump_search_results)

    # ------------------------------------------------------------------
    # Legacy API — these signatures match the previous DesktopApp.
    # ------------------------------------------------------------------

    def show_onboarding(self) -> None:
        self.onboarding.open()

    def show_popup(self) -> None:
        self.popup.open()

    def set_status(self, message: str) -> None:
        """Surface a transient status message. Empty string clears it.

        Used by the app's _pump_progress / _pump_errors handlers.
        Errors take priority over progress; progress over idle.
        """
        sb = self._status_bar
        # Defensive: the persistent StatusBar is built lazily (only
        # when the wizard or the popup is actually shown). If the
        # caller's thread fires before the bar exists, just store the
        # text and apply it when ``build()`` runs.
        if not hasattr(sb, "_text_var") or sb._text_var is None:
            self._idle_message = message
            return
        if not message:
            self._idle_message = ""
            try:
                sb.set_idle("")
            except tk.TclError:
                pass
            return
        if message.startswith("⚠"):
            try:
                sb.set_error(message.lstrip("⚠ ").strip())
            except tk.TclError:
                pass
        else:
            self._idle_message = message
            try:
                sb.set_idle(message)
            except tk.TclError:
                pass

    def run(self) -> None:
        self.root.mainloop()

    def _pump_search_results(self) -> None:
        """Legacy pump for callers that push payloads directly.

        The SearchPopup has its own internal pump. This one is here for
        any legacy code that pushes through ``_search_results`` directly.
        We guard aggressively because the pump can fire while the
        SearchPopup's window is being constructed, and we must not
        touch widgets that don't exist yet.
        """
        try:
            if self.popup is not None and self.popup.window is not None and self.popup.window.winfo_exists():
                latest: tuple[int, dict[str, Any]] | None = None
                while not self._search_results.empty():
                    latest = self._search_results.get_nowait()
                if latest is not None:
                    generation, payload = latest
                    if generation >= self._latest_rendered_generation:
                        self._latest_rendered_generation = generation
                        self.popup.show_results(payload)
        except (queue.Empty, tk.TclError):
            pass
        # Re-schedule.
        try:
            self.root.after(100, self._pump_search_results)
        except tk.TclError:
            pass


# ---------------------------------------------------------------------------
# Module-level helper
# ---------------------------------------------------------------------------


def set_status_silently(app: DesktopApp | None, message: str) -> None:
    """Set status without raising if the UI is not yet built.

    Used by error queues that fire on background threads before
    ``DesktopApp`` exists.
    """
    if app is None:
        return
    try:
        app.set_status(message)
    except tk.TclError:
        pass
