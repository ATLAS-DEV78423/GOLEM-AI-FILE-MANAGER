"""The onboarding wizard (4 steps, smooth transitions, async validation).

Layout
------

::

    +---------------------------------------------+
    |  o  o  o  o   Folders . Provider . Terms    |   <-- step indicator
    |                                              |
    |  Awaken GOLEM                                |   <-- title
    |  Tell GOLEM where to look and where to       |   <-- subtitle
    |  write.                                      |
    |                                              |
    |  +- Watched folder ---------------------+    |
    |  |  C:/Users/you/Documents/Inbox    [..]|    |
    |  +---------------------------------------+    |
    |  +- Obsidian vault ---------------------+    |
    |  |  C:/Users/you/Documents/Vault    [..]|    |
    |  +---------------------------------------+    |
    |                                              |
    |                          [ Back ]  [ Next ]  |
    +---------------------------------------------+

Steps
-----
1. Folders  - pick watched folder + Obsidian vault.
2. Provider - choose AI provider, model, base URL, API key. Async Test.
3. Terms    - read the bundled terms, accept.
4. Confirm  - summary screen with a final "Awaken GOLEM" CTA.

Transitions
-----------
A 220 ms fade + 12 px horizontal slide between steps. The step
indicator and the title bar persist; only the body pane is replaced.
"""
from __future__ import annotations

import inspect
import logging
import threading
import tkinter as tk
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .legal import TERMS_VERSION, terms_of_service_text
from .summarizer import PROVIDER_SPEC_MAP, check_provider_connection, provider_choices
from .ui_anim import fade_in, slide_in
from .ui_components import (
    PathField,
    PrimaryButton,
    SecondaryButton,
    SecretField,
    Separator,
    StatusBar,
    StepIndicator,
)
from .ui_icons import get_icon
from .ui_theme import COLORS, SIZE, SPACING, TYPOGRAPHY
from .ui_window import place_centered

_LOG = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Step labels
# ---------------------------------------------------------------------------


_STEPS = ["Folders", "Provider", "Terms", "Confirm"]


# ---------------------------------------------------------------------------
# Onboarding result
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class OnboardingResult:
    watched: str
    vault: str
    provider: str
    api_key: str
    model: str
    base_url: str
    terms_accepted: bool

    def to_legacy_args(self) -> tuple[str, str, str, str, str, str, bool]:
        return (
            self.watched, self.vault, self.provider,
            self.api_key, self.model, self.base_url, self.terms_accepted,
        )


# ---------------------------------------------------------------------------
# Wizard
# ---------------------------------------------------------------------------


class OnboardingWizard:
    """Multi-step setup wizard.

    ``on_save`` may accept either a single :class:`OnboardingResult` or
    the legacy 7-arg tuple. We detect via ``inspect.signature``.
    """

    def __init__(
        self,
        root: tk.Tk,
        on_save: Callable[..., None],
        initial: OnboardingResult | None = None,
    ):
        self.root = root
        self.on_save = on_save
        self.initial = initial
        self.window: tk.Toplevel | None = None
        self._terms_window: tk.Toplevel | None = None
        self._current_step: int = 0
        # Form state
        self.watched_var = tk.StringVar(value=initial.watched if initial else "")
        self.vault_var = tk.StringVar(value=initial.vault if initial else "")
        self.provider_label_var = tk.StringVar()
        self.api_var = tk.StringVar(value=initial.api_key if initial else "")
        self.model_var = tk.StringVar(value=initial.model if initial else "")
        self.base_url_var = tk.StringVar(value=initial.base_url if initial else "")
        self.terms_var = tk.BooleanVar(value=False)
        # Body widgets
        self._body: tk.Frame | None = None
        self._indicator: StepIndicator | None = None
        self._status_bar: StatusBar | None = None
        self._title_label: ttk.Label | None = None
        self._subtitle_label: ttk.Label | None = None
        self._back_btn: ttk.Button | None = None
        self._next_btn: ttk.Button | None = None
        self._secret: SecretField | None = None
        # Provider map
        self._provider_options = provider_choices()
        self._provider_label_by_key = {key: label for key, label in self._provider_options}
        self._provider_key_by_label = {label: key for key, label in self._provider_options}
        default_provider = initial.provider if initial else "heuristic"
        self.provider_label_var.set(
            self._provider_label_by_key.get(default_provider, self._provider_options[0][1])
        )

    # ------------------------------------------------------------------
    # Open / close
    # ------------------------------------------------------------------

    def open(self) -> None:
        if self.window and self.window.winfo_exists():
            try:
                self.window.deiconify()
                self.window.lift()
            except tk.TclError:
                pass
            return
        win = self._build_window()
        self.window = win
        try:
            place_centered(win, SIZE.onboarding_w, SIZE.onboarding_h)
        except Exception:
            win.geometry(f"{SIZE.onboarding_w}x{SIZE.onboarding_h}+100+60")
        try:
            win.attributes("-alpha", 0.0)
        except tk.TclError:
            pass
        win.update_idletasks()
        try:
            fade_in(win, duration_ms=200)
        except Exception:
            pass
        self._render_step(0)

    def hide(self) -> None:
        if not self.window or not self.window.winfo_exists():
            return
        try:
            self.window.withdraw()
        except tk.TclError:
            pass

    def close(self) -> None:
        if self.window:
            try:
                self.window.destroy()
            except tk.TclError:
                pass
            self.window = None

    # ------------------------------------------------------------------
    # Build shell
    # ------------------------------------------------------------------

    def _build_window(self) -> tk.Toplevel:
        win = tk.Toplevel(self.root)
        win.title("Awaken GOLEM")
        win.configure(bg=COLORS.bg.panel)
        win.minsize(SIZE.onboarding_w - 80, SIZE.onboarding_h - 200)
        win.bind("<Escape>", lambda _e: self.hide())
        win.protocol("WM_DELETE_WINDOW", self.hide)

        # Header: step indicator
        header = tk.Frame(win, bg=COLORS.bg.panel, height=56)
        header.pack(fill="x", padx=SPACING.xxl, pady=(SPACING.lg, 0))
        header.pack_propagate(False)
        self._indicator = StepIndicator(header, _STEPS, current=0)
        self._indicator.build().pack(side="left", fill="x", expand=True)

        # Title
        title_frame = tk.Frame(win, bg=COLORS.bg.panel)
        title_frame.pack(fill="x", padx=SPACING.xxl, pady=(SPACING.lg, 0))
        self._title_label = ttk.Label(title_frame, text="", style="Display.TLabel")
        self._title_label.pack(anchor="w")
        self._subtitle_label = ttk.Label(title_frame, text="", style="Body.TLabel")
        self._subtitle_label.pack(anchor="w", pady=(SPACING.xxs, 0))

        # Divider
        Separator(win).pack(fill="x", padx=SPACING.xxl, pady=SPACING.lg)

        # Body
        self._body = tk.Frame(win, bg=COLORS.bg.panel)
        self._body.pack(fill="both", expand=True, padx=SPACING.xxl, pady=(0, SPACING.lg))

        # Footer
        footer = tk.Frame(win, bg=COLORS.bg.titlebar, height=72)
        footer.pack(fill="x", side="bottom")
        footer.pack_propagate(False)
        footer_inner = tk.Frame(footer, bg=COLORS.bg.titlebar)
        footer_inner.pack(fill="x", padx=SPACING.xxl, pady=SPACING.md)
        # Use the footer frame as the StatusBar's parent so the icon
        # is owned by the wizard's Toplevel (not the withdrawn root).
        self._status_bar = StatusBar(footer_inner)
        self._status_bar.build().pack(side="left", fill="x", expand=True)
        self._back_btn = SecondaryButton(footer_inner, "Back", self._on_back, width=10)
        self._back_btn.pack(side="right", padx=(SPACING.sm, 0))
        self._next_btn = PrimaryButton(footer_inner, "Next", self._on_next, width=14)
        self._next_btn.pack(side="right")

        return win

    # ------------------------------------------------------------------
    # Step rendering
    # ------------------------------------------------------------------

    def _render_step(self, idx: int) -> None:
        self._current_step = max(0, min(idx, len(_STEPS) - 1))
        if self._indicator is not None:
            self._indicator.set_current(self._current_step)
        if self._body is not None:
            for child in list(self._body.winfo_children()):
                try:
                    child.destroy()
                except tk.TclError:
                    pass
        titles = [
            ("Awaken GOLEM", "Tell GOLEM where to look and where to write."),
            ("Choose your AI", "Pick a provider, or stay with Heuristic mode."),
            ("Terms of service", "A short read before GOLEM starts watching."),
            ("Ready to awaken", "One last look before GOLEM starts."),
        ]
        if self._title_label is not None:
            self._title_label.configure(text=titles[self._current_step][0])
        if self._subtitle_label is not None:
            self._subtitle_label.configure(text=titles[self._current_step][1])
        assert self._back_btn is not None and self._next_btn is not None
        if self._current_step == 0:
            try:
                self._back_btn.state(["disabled"])
            except tk.TclError:
                pass
        else:
            try:
                self._back_btn.state(["!disabled"])
            except tk.TclError:
                pass
        if self._current_step == len(_STEPS) - 1:
            self._next_btn.configure(text="Awaken GOLEM")
        else:
            self._next_btn.configure(text="Next")
        renderers = [
            self._render_folders,
            self._render_provider,
            self._render_terms,
            self._render_confirm,
        ]
        try:
            renderers[self._current_step]()
        except Exception:
            _LOG.exception("step %d render failed", self._current_step)
        # Slide-in + fade animation for step transitions
        if self.window is not None:
            try:
                # Animate opacity for smoother step transitions
                self.window.attributes("-alpha", 0.88)
                self.window.update_idletasks()
                self.window.after(50, lambda: self._animate_step_in())
            except Exception:
                pass

    def _animate_step_in(self) -> None:
        """Gently bump alpha back up and slide slightly for step transitions."""
        if self.window is None or not self.window.winfo_exists():
            return
        try:
            slide_in(self.window, duration_ms=220, from_dy=8)
            fade_in(self.window, duration_ms=200, from_alpha=0.88, to_alpha=1.0)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Step 1: Folders
    # ------------------------------------------------------------------

    @staticmethod
    def _find_obsidian_vaults() -> list[Path]:
        """Auto-detect Obsidian vaults from common locations."""
        candidates: list[Path] = []
        home = Path.home()

        # Common vault locations, ordered by likelihood
        search_paths = [
            home / "Documents" / "Obsidian",
            home / "Documents" / "Obsidian Vault",
            home / "Documents" / "Vault",
            home / "Obsidian",
            home / "Obsidian Vault",
            home / "Desktop",
            home / "Documents",
        ]

        # Also check for Obsidian .obsidian folder marker
        for root_dir in [home / "Documents", home]:
            try:
                for entry in root_dir.iterdir():
                    if entry.is_dir() and not entry.name.startswith("."):
                        if (entry / ".obsidian").is_dir():
                            candidates.append(entry)
            except (PermissionError, OSError):
                continue

        for sp in search_paths:
            if sp not in candidates and sp.is_dir() and (sp / ".obsidian").is_dir():
                candidates.append(sp)

        return candidates[:3]

    def _auto_detect_vault(self) -> None:
        """Auto-fill the vault field if we find one."""
        if self.vault_var.get().strip():
            return  # Already set
        vaults = self._find_obsidian_vaults()
        if vaults:
            self.vault_var.set(str(vaults[0]))
            self._validate_folders_live()

    def _render_folders(self) -> None:
        body = self._body
        assert body is not None
        PathField(
            parent=body,
            label="Watched folder",
            variable=self.watched_var,
            on_browse=lambda: self._browse_folder(self.watched_var, "Pick the folder GOLEM should watch"),
        ).build().pack(fill="x", pady=(0, SPACING.md))
        ttk.Label(
            body,
            text="Drop a file here and GOLEM will index it within seconds.",
            style="Caption.TLabel", wraplength=480, justify="left",
        ).pack(anchor="w", pady=(0, SPACING.lg))

        self._auto_detect_vault()
        PathField(
            parent=body,
            label="Obsidian vault",
            variable=self.vault_var,
            on_browse=lambda: self._browse_folder(self.vault_var, "Pick your Obsidian vault"),
        ).build().pack(fill="x", pady=(0, SPACING.md))
        ttk.Label(
            body,
            text="GOLEM will write a note for each file into this vault.",
            style="Caption.TLabel", wraplength=480, justify="left",
        ).pack(anchor="w", pady=(0, SPACING.lg))

        # Help / hint
        info = tk.Frame(body, bg=COLORS.state.info_muted, bd=0, highlightthickness=0)
        info.pack(fill="x", pady=(SPACING.lg, 0))
        info_inner = tk.Frame(info, bg=COLORS.state.info_muted)
        info_inner.pack(fill="x", padx=SPACING.md, pady=SPACING.sm)
        ttk.Label(
            info_inner, image=get_icon("info", size=14, color=COLORS.state.info, master=info_inner),
            text=" Tip", compound="left", style="Caption.TLabel",
        ).pack(side="left", padx=(0, SPACING.xs))
        ttk.Label(
            info_inner,
            text="You can change these paths later from the tray menu.",
            style="Caption.TLabel", foreground=COLORS.state.info,
        ).pack(side="left")
        if self._status_bar is not None:
            self._status_bar.set_idle("Step 1 of 4 - pick the folders")

    def _browse_folder(self, var: tk.StringVar, title: str) -> None:
        folder = filedialog.askdirectory(parent=self.window, title=title, mustexist=True)
        if folder:
            var.set(folder)
            self._validate_folders_live()

    def _validate_folders_live(self) -> bool:
        ok = True
        for var, label in ((self.watched_var, "Watched folder"), (self.vault_var, "Vault")):
            value = var.get().strip()
            if not value:
                if self._status_bar is not None:
                    self._status_bar.set_warning(f"{label} is empty")
                ok = False
            elif not Path(value).exists():
                if self._status_bar is not None:
                    self._status_bar.set_warning(f"{label} does not exist")
                ok = False
        if ok and self._status_bar is not None:
            self._status_bar.set_idle("Step 1 of 4 - pick the folders")
        return ok

    # ------------------------------------------------------------------
    # Step 2: Provider
    # ------------------------------------------------------------------

    def _render_provider(self) -> None:
        body = self._body
        assert body is not None
        ttk.Label(body, text="AI provider", style="Caption.TLabel").pack(anchor="w", pady=(0, SPACING.xs))
        combo = ttk.Combobox(
            body,
            textvariable=self.provider_label_var,
            values=[label for _, label in self._provider_options],
            state="readonly",
        )
        combo.pack(fill="x", pady=(0, SPACING.xs))
        combo.bind("<<ComboboxSelected>>", lambda _e: self._sync_provider_defaults())

        ttk.Label(
            body,
            text=("Heuristic mode is fast, local, and doesn't need an API key. "
                  "Choose a provider for AI summaries and search reranking."),
            style="Caption.TLabel", wraplength=480, justify="left",
        ).pack(anchor="w", pady=(0, SPACING.lg))

        ttk.Label(body, text="Model (optional)", style="Caption.TLabel").pack(anchor="w", pady=(0, SPACING.xs))
        ttk.Entry(body, textvariable=self.model_var).pack(fill="x", pady=(0, SPACING.md))

        ttk.Label(body, text="API base URL (optional)", style="Caption.TLabel").pack(anchor="w", pady=(0, SPACING.xs))
        ttk.Entry(body, textvariable=self.base_url_var).pack(fill="x", pady=(0, SPACING.lg))

        self._secret = SecretField(
            parent=body,
            label="API key",
            variable=self.api_var,
            test_async=self._test_api_key_async,
        )
        self._secret.build().pack(fill="x", pady=(0, SPACING.md))

        if self._status_bar is not None:
            self._status_bar.set_idle("Step 2 of 4 - pick a provider and test your key")

        self._sync_provider_defaults()

    def _sync_provider_defaults(self) -> None:
        label = self.provider_label_var.get()
        provider_key = self._provider_key_by_label.get(label, "heuristic")
        spec = PROVIDER_SPEC_MAP.get(provider_key)
        if spec is None:
            return
        if not self.model_var.get().strip():
            self.model_var.set(spec.default_model)
        if not self.base_url_var.get().strip() and spec.base_url:
            self.base_url_var.set(spec.base_url)

    def _test_api_key_async(self) -> None:
        if self._secret is None:
            return
        provider_label = self.provider_label_var.get()
        provider_key = self._provider_key_by_label.get(provider_label, "heuristic")
        if provider_key in {"heuristic", "none", "off"}:
            self._secret.set_result(True, "Heuristic mode does not need a key.")
            return
        api_value = self.api_var.get().strip()
        if not api_value:
            self._secret.set_result(False, "Enter an API key first.")
            return
        self._secret.set_testing("Testing")
        def _worker():
            try:
                ok, msg = check_provider_connection(
                    provider_key,
                    api_value,
                    self.model_var.get().strip(),
                    self.base_url_var.get().strip(),
                )
            except Exception as exc:
                ok, msg = False, str(exc)
            if self.window is not None:
                try:
                    self.window.after(0, lambda: self._secret.set_result(ok, msg))
                except tk.TclError:
                    pass
        threading.Thread(target=_worker, daemon=True, name="golem-test-key").start()

    # ------------------------------------------------------------------
    # Step 3: Terms
    # ------------------------------------------------------------------

    def _render_terms(self) -> None:
        body = self._body
        assert body is not None
        header = tk.Frame(body, bg=COLORS.bg.panel)
        header.pack(fill="x", pady=(0, SPACING.md))
        ttk.Label(
            header, text=f"Terms of Service v{TERMS_VERSION}",
            style="BodyStrong.TLabel",
        ).pack(side="left")
        SecondaryButton(header, "Read full terms", self._open_terms, width=18).pack(side="right")

        card = tk.Frame(body, bg=COLORS.bg.elevated, bd=0, highlightthickness=0)
        card.pack(fill="both", expand=True, pady=(0, SPACING.md))
        card_inner = tk.Frame(card, bg=COLORS.bg.elevated)
        card_inner.pack(fill="both", expand=True, padx=SPACING.lg, pady=SPACING.lg)
        for headline, body_text in [
            ("What GOLEM does", "Watches a folder, extracts text, writes notes."),
            ("Where your data goes", "Locally only. Nothing leaves your machine unless you pick a cloud AI provider."),
            ("Your responsibility", "Don't point GOLEM at folders with secrets you don't want indexed."),
        ]:
            block = tk.Frame(card_inner, bg=COLORS.bg.elevated)
            block.pack(fill="x", anchor="w", pady=(0, SPACING.md))
            ttk.Label(block, text=headline, style="BodyStrong.TLabel").pack(anchor="w")
            ttk.Label(block, text=body_text, style="Caption.TLabel", wraplength=420, justify="left").pack(anchor="w", pady=(SPACING.xxs, 0))
        ttk.Checkbutton(
            body,
            text="I agree to the Terms of Service",
            variable=self.terms_var,
        ).pack(anchor="w", pady=(SPACING.md, 0))
        if self._status_bar is not None:
            self._status_bar.set_idle("Step 3 of 4 - accept the terms")

    def _open_terms(self) -> None:
        if self._terms_window and self._terms_window.winfo_exists():
            self._terms_window.deiconify()
            self._terms_window.lift()
            return
        win = tk.Toplevel(self.root)
        win.title(f"GOLEM Terms of Service v{TERMS_VERSION}")
        win.configure(bg=COLORS.bg.panel)
        win.geometry("760x720")
        win.minsize(640, 520)
        frame = tk.Frame(win, bg=COLORS.bg.panel)
        frame.pack(fill="both", expand=True, padx=SPACING.lg, pady=SPACING.lg)
        ttk.Label(frame, text=f"Terms of Service v{TERMS_VERSION}", style="Title.TLabel").pack(anchor="w", pady=(0, SPACING.md))
        text_frame = tk.Frame(frame, bg=COLORS.bg.panel)
        text_frame.pack(fill="both", expand=True)
        scrollbar = ttk.Scrollbar(text_frame, style="Vertical.TScrollbar")
        scrollbar.pack(side="right", fill="y")
        text = tk.Text(
            text_frame, wrap="word", yscrollcommand=scrollbar.set,
            bg=COLORS.bg.elevated, fg=COLORS.fg.primary,
            insertbackground=COLORS.accent.DEFAULT,
            relief="flat", bd=0, highlightthickness=1,
            highlightbackground=COLORS.border.subtle,
            highlightcolor=COLORS.border.subtle,
            font=TYPOGRAPHY.body.font(),
            padx=SPACING.md, pady=SPACING.md,
        )
        text.pack(side="left", fill="both", expand=True)
        scrollbar.config(command=text.yview)
        text.insert("1.0", terms_of_service_text())
        text.configure(state="disabled")
        ttk.Label(
            frame, text="Read the terms before continuing.",
            style="Caption.TLabel",
        ).pack(anchor="w", pady=(SPACING.md, 0))
        self._terms_window = win

    # ------------------------------------------------------------------
    # Step 4: Confirm
    # ------------------------------------------------------------------

    def _render_confirm(self) -> None:
        body = self._body
        assert body is not None
        provider_label = self.provider_label_var.get()
        provider_key = self._provider_key_by_label.get(provider_label, "heuristic")

        card = tk.Frame(body, bg=COLORS.bg.elevated, bd=0, highlightthickness=0)
        card.pack(fill="x", pady=(0, SPACING.lg))
        card_inner = tk.Frame(card, bg=COLORS.bg.elevated)
        card_inner.pack(fill="x", padx=SPACING.lg, pady=SPACING.lg)

        rows = [
            ("Watched folder", self.watched_var.get() or "-"),
            ("Obsidian vault", self.vault_var.get() or "-"),
            ("AI provider", provider_label or "-"),
            ("Model", self.model_var.get() or "(default)"),
        ]
        for label, value in rows:
            r = tk.Frame(card_inner, bg=COLORS.bg.elevated)
            r.pack(fill="x", pady=SPACING.xs)
            ttk.Label(r, text=label, style="Caption.TLabel", width=18, anchor="w").pack(side="left")
            ttk.Label(r, text=value, style="Body.TLabel").pack(side="left", fill="x", expand=True)

        if provider_key != "heuristic":
            api = self.api_var.get()
            masked = ("*" * min(8, len(api)) + api[-4:]) if len(api) >= 12 else "(none)"
            ttk.Label(card_inner, text=f"API key: {masked}", style="Caption.TLabel").pack(anchor="w", pady=(SPACING.sm, 0))

        next_card = tk.Frame(body, bg=COLORS.bg.panel, bd=0, highlightthickness=0)
        next_card.pack(fill="x")
        ttk.Label(next_card, text="When you click Awaken GOLEM:", style="BodyStrong.TLabel").pack(anchor="w")
        for line in [
            "1. The watched folder is scanned for new and changed files.",
            "2. Each file gets a note in your Obsidian vault.",
            "3. Files are moved into <vault>/GOLEM Files/<category>/.",
            "4. The tray icon appears - right-click it for more actions.",
        ]:
            ttk.Label(next_card, text=line, style="Caption.TLabel").pack(anchor="w", pady=(SPACING.xxs, 0))
        if self._status_bar is not None:
            self._status_bar.set_idle("Step 4 of 4 - confirm")

    # ------------------------------------------------------------------
    # Nav
    # ------------------------------------------------------------------

    def _on_back(self) -> None:
        if self._current_step == 0:
            return
        self._render_step(self._current_step - 1)

    def _on_next(self) -> None:
        if self._current_step == 0:
            ok, msg = self._validate_folders()
            if not ok:
                if self._status_bar is not None:
                    self._status_bar.set_error(msg)
                return
        elif self._current_step == 1:
            ok, msg = self._validate_provider()
            if not ok:
                if self._status_bar is not None:
                    self._status_bar.set_error(msg)
                return
        elif self._current_step == 2:
            if not self.terms_var.get():
                if self._status_bar is not None:
                    self._status_bar.set_error("You must accept the Terms of Service to continue.")
                return
        elif self._current_step == len(_STEPS) - 1:
            self._save()
            return
        self._render_step(self._current_step + 1)

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def _validate_folders(self) -> tuple[bool, str]:
        watched = self.watched_var.get().strip()
        vault = self.vault_var.get().strip()
        if not watched or not vault:
            return False, "Choose both a watched folder and a vault."
        if not Path(watched).exists():
            return False, f"Watched folder does not exist: {watched}"
        if not Path(vault).exists():
            return False, f"Vault does not exist: {vault}"
        if Path(watched).resolve() == Path(vault).resolve():
            return False, "The watched folder and the vault must be different paths."
        return True, ""

    def _validate_provider(self) -> tuple[bool, str]:
        label = self.provider_label_var.get()
        provider_key = self._provider_key_by_label.get(label, "heuristic")
        if provider_key == "heuristic":
            return True, ""
        api = self.api_var.get().strip()
        if not api:
            return False, "Enter an API key or switch to Heuristic mode."
        if len(api) < 20:
            if not messagebox.askyesno(
                "GOLEM",
                "That API key looks unusually short. Most provider keys are 30+ characters. "
                "Continue anyway?",
            ):
                return False, "Provide a longer API key."
        if provider_key == "custom_openai" and not self.base_url_var.get().strip():
            return False, "Enter a base URL for the custom OpenAI-compatible provider."
        return True, ""

    # ------------------------------------------------------------------
    # Save
    # ------------------------------------------------------------------

    def _save(self) -> None:
        watched = self.watched_var.get().strip()
        vault = self.vault_var.get().strip()
        provider_label = self.provider_label_var.get().strip()
        provider = self._provider_key_by_label.get(provider_label, "heuristic")
        api = self.api_var.get().strip()
        model = self.model_var.get().strip()
        base_url = self.base_url_var.get().strip()
        accepted = bool(self.terms_var.get())
        if not accepted:
            if self._status_bar is not None:
                self._status_bar.set_error("You must accept the Terms of Service to continue.")
            return
        result = OnboardingResult(
            watched=watched, vault=vault, provider=provider,
            api_key=api, model=model, base_url=base_url,
            terms_accepted=accepted,
        )
        try:
            sig = inspect.signature(self.on_save)
            if len(sig.parameters) == 7:
                self.on_save(*result.to_legacy_args())
            else:
                self.on_save(result)
        except Exception:
            _LOG.exception("on_save failed")
            if self._status_bar is not None:
                self._status_bar.set_error("Save failed. See log for details.")
            return
        self.close()
