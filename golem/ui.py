from __future__ import annotations

import queue
import threading
import tkinter as tk
from dataclasses import dataclass
from tkinter import filedialog, messagebox, ttk
from typing import Any, Callable

from .legal import TERMS_VERSION, terms_of_service_text
from .summarizer import PROVIDER_SPEC_MAP, provider_choices


@dataclass(slots=True)
class UIConfig:
    title: str = "GOLEM"
    width: int = 420
    height: int = 520


class SearchPopup:
    def __init__(self, root: tk.Tk, on_search: Callable[[str], None], on_open: Callable[[str], None], on_reveal: Callable[[str], None]):
        self.root = root
        self.on_search = on_search
        self.on_open = on_open
        self.on_reveal = on_reveal
        self.window: tk.Toplevel | None = None
        self.listbox: tk.Listbox | None = None
        self.entry: tk.Entry | None = None
        self.status: tk.Label | None = None
        self.results: list[dict[str, Any]] = []
        self._search_after_id: str | None = None

    def open(self) -> None:
        if self.window and self.window.winfo_exists():
            self.window.deiconify()
            self.window.lift()
            self.entry.focus_set()
            return
        win = tk.Toplevel(self.root)
        win.title("GOLEM Search")
        win.geometry("420x520")
        win.configure(bg="#0f0f0f")
        win.attributes("-topmost", True)
        win.bind("<Escape>", lambda _event: win.withdraw())
        win.protocol("WM_DELETE_WINDOW", win.withdraw)
        self.window = win

        entry = tk.Entry(win, font=("Segoe UI", 13))
        entry.pack(fill="x", padx=12, pady=(12, 8))
        entry.bind("<Return>", self._submit)
        entry.bind("<KeyRelease>", self._typeahead)
        self.entry = entry

        status = tk.Label(win, text="Describe what you are looking for...", bg="#0f0f0f", fg="#c8c8c8")
        status.pack(fill="x", padx=12, pady=(0, 8))
        self.status = status

        listbox = tk.Listbox(win, font=("Segoe UI", 11), height=20)
        listbox.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        listbox.bind("<Double-Button-1>", self._open_selected)
        listbox.bind("<Button-3>", self._reveal_selected)
        self.listbox = listbox

    def show_results(self, results: list[dict[str, Any]], message: str | None = None) -> None:
        self.results = results
        if not self.listbox:
            return
        self.listbox.delete(0, tk.END)
        for row in results:
            label = f"{row.get('clean_filename') or row.get('original_filename')}"
            summary = row.get("summary") or ""
            category = row.get("category") or ""
            confidence = row.get("confidence")
            suffix = f" [{category}]"
            if confidence is not None:
                suffix += f" {confidence:.2f}"
            if summary:
                self.listbox.insert(tk.END, f"{label}{suffix} - {summary}")
            else:
                self.listbox.insert(tk.END, f"{label}{suffix}")
        if message and self.status:
            self.status.configure(text=message)

    def set_status(self, message: str) -> None:
        if self.status:
            self.status.configure(text=message)

    def _submit(self, _event=None) -> None:
        if not self.entry:
            return
        if self._search_after_id is not None:
            try:
                self.root.after_cancel(self._search_after_id)
            except Exception:
                pass
            self._search_after_id = None
        query = self.entry.get().strip()
        if query:
            self.on_search(query)

    def _typeahead(self, _event=None) -> None:
        if not self.entry:
            return
        query = self.entry.get().strip()
        if self._search_after_id is not None:
            try:
                self.root.after_cancel(self._search_after_id)
            except Exception:
                pass
            self._search_after_id = None
        if len(query) >= 3:
            self._search_after_id = self.root.after(250, lambda q=query: self.on_search(q))

    def _selected_path(self) -> str | None:
        if not self.listbox:
            return None
        index = self.listbox.curselection()
        if not index:
            return None
        row_index = index[0]
        if row_index >= len(self.results):
            return None
        row = self.results[row_index]
        return str(row.get("current_path") or row.get("original_path") or "")

    def _open_selected(self, _event=None) -> None:
        path = self._selected_path()
        if path:
            self.on_open(path)

    def _reveal_selected(self, _event=None) -> None:
        path = self._selected_path()
        if path:
            self.on_reveal(path)


class OnboardingWizard:
    def __init__(self, root: tk.Tk, on_save: Callable[[str, str, str, str, str, str, bool], None]):
        self.root = root
        self.on_save = on_save
        self.window: tk.Toplevel | None = None
        self._terms_window: tk.Toplevel | None = None

    def _open_terms(self) -> None:
        if self._terms_window and self._terms_window.winfo_exists():
            self._terms_window.deiconify()
            self._terms_window.lift()
            return
        win = tk.Toplevel(self.root)
        win.title("GOLEM Terms of Service")
        win.geometry("760x720")
        win.minsize(640, 520)
        win.configure(bg="#111111")
        win.attributes("-topmost", True)
        self._terms_window = win

        frame = tk.Frame(win, bg="#111111")
        frame.pack(fill="both", expand=True, padx=14, pady=14)

        title = tk.Label(frame, text=f"Terms of Service v{TERMS_VERSION}", font=("Segoe UI", 16, "bold"), bg="#111111", fg="#e8e8e8")
        title.pack(anchor="w", pady=(0, 10))

        text_frame = tk.Frame(frame, bg="#111111")
        text_frame.pack(fill="both", expand=True)
        scrollbar = tk.Scrollbar(text_frame)
        scrollbar.pack(side="right", fill="y")
        text = tk.Text(text_frame, wrap="word", yscrollcommand=scrollbar.set, font=("Segoe UI", 10), bg="#f8f8f8", fg="#222222")
        text.pack(fill="both", expand=True)
        scrollbar.config(command=text.yview)
        text.insert("1.0", terms_of_service_text())
        text.configure(state="disabled")

        footer = tk.Label(frame, text="Read the terms before continuing. This copy ships with the app.", bg="#111111", fg="#c8c8c8")
        footer.pack(anchor="w", pady=(10, 0))

    def open(self) -> None:
        if self.window and self.window.winfo_exists():
            self.window.deiconify()
            self.window.lift()
            return
        win = tk.Toplevel(self.root)
        win.title("GOLEM Setup")
        win.geometry("560x650")
        win.minsize(560, 650)
        win.configure(bg="#111111")
        win.attributes("-topmost", True)
        self.window = win

        title = tk.Label(win, text="Awaken GOLEM", font=("Segoe UI", 20, "bold"), bg="#111111", fg="#e8e8e8")
        title.pack(pady=(20, 10))

        watched_var = tk.StringVar()
        vault_var = tk.StringVar()
        provider_options = provider_choices()
        provider_label_by_key = {key: label for key, label in provider_options}
        provider_key_by_label = {label: key for key, label in provider_options}
        provider_var = tk.StringVar(value=provider_label_by_key.get("heuristic", provider_options[0][1]))
        model_var = tk.StringVar(value="")
        base_url_var = tk.StringVar(value="")
        api_var = tk.StringVar()
        terms_var = tk.BooleanVar(value=False)

        def folder_row(label: str, variable: tk.StringVar, command: Callable[[], None]):
            frame = tk.Frame(win, bg="#111111")
            frame.pack(fill="x", padx=18, pady=8)
            tk.Label(frame, text=label, bg="#111111", fg="#e8e8e8", anchor="w").pack(fill="x")
            row = tk.Frame(frame, bg="#111111")
            row.pack(fill="x")
            tk.Entry(row, textvariable=variable).pack(side="left", fill="x", expand=True)
            tk.Button(row, text="Browse", command=command).pack(side="left", padx=8)

        def text_row(label: str, variable: tk.StringVar):
            frame = tk.Frame(win, bg="#111111")
            frame.pack(fill="x", padx=18, pady=8)
            tk.Label(frame, text=label, bg="#111111", fg="#e8e8e8", anchor="w").pack(fill="x")
            tk.Entry(frame, textvariable=variable).pack(fill="x")

        def choose_watched():
            folder = filedialog.askdirectory(parent=win)
            if folder:
                watched_var.set(folder)

        def choose_vault():
            folder = filedialog.askdirectory(parent=win)
            if folder:
                vault_var.set(folder)

        folder_row("Watched folder", watched_var, choose_watched)
        folder_row("Obsidian vault", vault_var, choose_vault)

        provider_frame = tk.Frame(win, bg="#111111")
        provider_frame.pack(fill="x", padx=18, pady=8)
        tk.Label(provider_frame, text="AI provider", bg="#111111", fg="#e8e8e8", anchor="w").pack(fill="x")
        provider_combo = ttk.Combobox(provider_frame, textvariable=provider_var, values=[label for _, label in provider_options], state="readonly")
        provider_combo.pack(fill="x")

        text_row("Model", model_var)
        text_row("API base URL (optional for custom providers)", base_url_var)

        api_frame = tk.Frame(win, bg="#111111")
        api_frame.pack(fill="x", padx=18, pady=8)
        tk.Label(api_frame, text="API key", bg="#111111", fg="#e8e8e8", anchor="w").pack(fill="x")
        tk.Entry(api_frame, textvariable=api_var, show="*").pack(fill="x")

        terms_frame = tk.Frame(win, bg="#111111")
        terms_frame.pack(fill="x", padx=18, pady=(8, 4))
        tk.Button(terms_frame, text="View Terms of Service", command=self._open_terms).pack(side="left")
        tk.Checkbutton(terms_frame, text="I agree to the Terms of Service", variable=terms_var, bg="#111111", fg="#e8e8e8", selectcolor="#111111", activebackground="#111111", activeforeground="#e8e8e8").pack(side="left", padx=(12, 0))

        provider_note = tk.Label(
            win,
            text="Heuristic mode works without an API key. Choose a provider if you want AI summaries and search reranking.",
            wraplength=520,
            justify="left",
            bg="#111111",
            fg="#c8c8c8",
        )
        provider_note.pack(fill="x", padx=18, pady=(8, 0))

        def sync_provider_defaults(event=None):
            label = provider_var.get()
            provider_key = provider_key_by_label.get(label, "heuristic")
            spec = PROVIDER_SPEC_MAP.get(provider_key)
            if not spec:
                return
            if not model_var.get().strip():
                model_var.set(spec.default_model)
            if not base_url_var.get().strip() and spec.base_url:
                base_url_var.set(spec.base_url)

        provider_combo.bind("<<ComboboxSelected>>", sync_provider_defaults)
        sync_provider_defaults()

        def save():
            watched = watched_var.get().strip()
            vault = vault_var.get().strip()
            provider_label = provider_var.get().strip()
            provider = provider_key_by_label.get(provider_label, "heuristic")
            api = api_var.get().strip()
            model = model_var.get().strip()
            base_url = base_url_var.get().strip()
            if not watched or not vault:
                messagebox.showerror("GOLEM", "Choose both a watched folder and a vault.")
                return
            if not terms_var.get():
                messagebox.showerror("GOLEM", "You must accept the Terms of Service to continue.")
                return
            if provider != "heuristic" and not api:
                messagebox.showerror("GOLEM", "Enter an API key or switch to Heuristic mode.")
                return
            if provider == "custom_openai" and not base_url:
                messagebox.showerror("GOLEM", "Enter a base URL for the custom OpenAI-compatible provider.")
                return
            self.on_save(watched, vault, provider, api, model, base_url, terms_var.get())
            win.destroy()

        tk.Button(win, text="Awaken GOLEM", bg="#b87333", fg="white", command=save).pack(fill="x", padx=18, pady=20)


class DesktopApp:
    def __init__(self, on_search: Callable[[str], list[dict[str, Any]]], on_open: Callable[[str], None], on_reveal: Callable[[str], None], on_save_config: Callable[[str, str, str, str, str, str, bool], None]):
        self.root = tk.Tk()
        self.root.withdraw()
        self.popup = SearchPopup(self.root, self._handle_search, on_open, on_reveal)
        self.onboarding = OnboardingWizard(self.root, on_save_config)
        self._search_handler = on_search
        self._search_results: "queue.Queue[tuple[int, list[dict[str, Any]]]]" = queue.Queue()
        self._search_generation = 0
        self._latest_rendered_generation = 0
        self.root.after(100, self._pump_search_results)

    def _handle_search(self, query: str) -> None:
        self._search_generation += 1
        generation = self._search_generation
        self.popup.set_status("Searching...")

        def worker() -> None:
            try:
                results = self._search_handler(query)
            except Exception as exc:
                results = [{"status": "not_found", "results": [], "message": f"Search failed: {exc}"}]
            self._search_results.put((generation, results))

        threading.Thread(target=worker, daemon=True).start()

    def _pump_search_results(self) -> None:
        latest: tuple[int, list[dict[str, Any]]] | None = None
        while not self._search_results.empty():
            latest = self._search_results.get_nowait()
        if latest is not None:
            generation, payload = latest
            if generation >= self._latest_rendered_generation:
                self._latest_rendered_generation = generation
                if payload and payload[0].get("status") == "not_found":
                    self.popup.show_results(payload[0]["results"], payload[0].get("message"))
                else:
                    self.popup.show_results(payload, None)
        self.root.after(100, self._pump_search_results)

    def show_onboarding(self) -> None:
        self.onboarding.open()

    def show_popup(self) -> None:
        self.popup.open()

    def set_status(self, message: str) -> None:
        self.popup.set_status(message)

    def run(self) -> None:
        self.root.mainloop()
