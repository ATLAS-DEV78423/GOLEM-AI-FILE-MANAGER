from __future__ import annotations

import json
import logging
import os
import re
import time
import threading
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote
from urllib import error, request

from .constants import DEFAULT_CATEGORY
from .utils import humanize_filename, normalize_tags, text_excerpt, tokenize


@dataclass(slots=True)
class FileMetadata:
    summary: str
    tags: list[str]
    key_contents: str
    category: str
    clean_name: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "summary": self.summary,
            "tags": self.tags,
            "key_contents": self.key_contents,
            "category": self.category,
            "clean_name": self.clean_name,
        }


class BaseSummarizer:
    fallback: "BaseSummarizer | None" = None

    def get_file_metadata(self, filename: str, text_snippet: str) -> FileMetadata:
        raise NotImplementedError

    def search_rerank(self, query: str, candidates: list[dict[str, Any]]) -> str:
        raise NotImplementedError


@dataclass(frozen=True, slots=True)
class ProviderSpec:
    key: str
    label: str
    kind: str
    base_url: str
    default_model: str


PROVIDER_SPECS: tuple[ProviderSpec, ...] = (
    ProviderSpec("heuristic", "Heuristic (no API)", "heuristic", "", ""),
    ProviderSpec("groq", "Groq", "openai_compatible", "https://api.groq.com/openai/v1", "llama-3.1-8b-instant"),
    ProviderSpec("openai", "OpenAI / ChatGPT", "openai_compatible", "https://api.openai.com/v1", "gpt-4o-mini"),
    ProviderSpec("openrouter", "OpenRouter", "openai_compatible", "https://openrouter.ai/api/v1", "openai/gpt-4o-mini"),
    ProviderSpec("xai", "xAI", "openai_compatible", "https://api.x.ai/v1", "grok-4.3"),
    ProviderSpec("nvidia_nim", "NVIDIA NIM", "openai_compatible", "https://integrate.api.nvidia.com/v1", "meta/llama-3.1-70b-instruct"),
    ProviderSpec("anthropic", "Anthropic / Claude", "anthropic", "https://api.anthropic.com/v1", "claude-3-5-sonnet-latest"),
    ProviderSpec("gemini", "Google Gemini", "gemini", "https://generativelanguage.googleapis.com/v1beta", "gemini-2.5-flash"),
    ProviderSpec("custom_openai", "Custom OpenAI-compatible", "openai_compatible", "", "gpt-4o-mini"),
)

PROVIDER_SPEC_MAP = {spec.key: spec for spec in PROVIDER_SPECS}


# Environment variable names for each provider. When the user has not
# entered a key in the onboarding wizard, ``build_summarizer`` will fall
# back to these. Set the variable in the user's environment (e.g. via the
# system Settings) and GOLEM will pick it up automatically.
PROVIDER_ENV_KEYS: dict[str, str] = {
    "groq": "GROQ_API_KEY",
    "openai": "OPENAI_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
    "xai": "XAI_API_KEY",
    "nvidia_nim": "NVIDIA_NIM_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "gemini": "GOOGLE_API_KEY",
}


def provider_choices() -> list[tuple[str, str]]:
    return [(spec.key, spec.label) for spec in PROVIDER_SPECS]


class HeuristicSummarizer(BaseSummarizer):
    def get_file_metadata(self, filename: str, text_snippet: str) -> FileMetadata:
        text = text_excerpt(text_snippet or "", 300)
        tags = self._tags_from_text(text)
        category = self._category_from_text(text, filename)
        summary = self._summary_from_text(filename, text)
        key_contents = ", ".join(tags[:5]) if tags else "general notes"
        clean_name = humanize_filename(filename)
        return FileMetadata(summary=summary, tags=tags, key_contents=key_contents, category=category, clean_name=clean_name)

    def search_rerank(self, query: str, candidates: list[dict[str, Any]]) -> str:
        query_tokens = set(tokenize(query))
        best: tuple[int, str] | None = None
        for candidate in candidates:
            haystack = " ".join(
                [
                    str(candidate.get("clean_filename", "")),
                    str(candidate.get("summary", "")),
                    str(candidate.get("tags", "")),
                    str(candidate.get("key_contents", "")),
                    str(candidate.get("category", "")),
                ]
            ).lower()
            score = sum(1 for token in query_tokens if token in haystack)
            if best is None or score > best[0]:
                best = (score, str(candidate.get("current_path") or candidate.get("original_path") or ""))
        return "NOT_FOUND" if best is None or best[0] == 0 else best[1]

    def _summary_from_text(self, filename: str, text: str) -> str:
        if not text:
            return f"File named {humanize_filename(filename)}."
        sentence = re.split(r"(?<=[.!?])\s+", text.strip())[0]
        return text_excerpt(sentence, 160) or f"File named {humanize_filename(filename)}."

    def _tags_from_text(self, text: str) -> list[str]:
        tokens = tokenize(text)
        if not tokens:
            return []
        stop = {
            "the",
            "and",
            "for",
            "with",
            "this",
            "that",
            "from",
            "have",
            "will",
            "your",
            "file",
            "document",
            "page",
        }
        freq: dict[str, int] = {}
        for token in tokens:
            if token in stop or len(token) < 3:
                continue
            freq[token] = freq.get(token, 0) + 1
        ordered = sorted(freq.items(), key=lambda item: (-item[1], item[0]))
        return normalize_tags([token for token, _ in ordered[:8]])

    def _category_from_text(self, text: str, filename: str) -> str:
        corpus = f"{filename} {text}".lower()
        mapping = {
            "Finance": ("invoice", "budget", "bank", "receipt", "tax", "expense", "payment"),
            "Research": ("paper", "study", "experiment", "research", "analysis", "dataset", "method"),
            "Design": ("design", "mockup", "ui", "ux", "wireframe", "visual", "brand"),
            "Code": ("code", "python", "java", "javascript", "function", "class", "api", "commit"),
            "Media": ("video", "audio", "image", "photo", "media", "clip"),
            "Personal": ("personal", "family", "home", "journal", "resume", "cv"),
            "Legal": ("contract", "agreement", "legal", "clause", "policy", "compliance"),
        }
        for category, keywords in mapping.items():
            if any(keyword in corpus for keyword in keywords):
                return category
        return DEFAULT_CATEGORY


# Module-level rate limiter shared across all summarizer instances, keyed by
# the API key. Different providers (or different accounts) get their own slot.
# Default: one call per second with a burst of 4 (then refill at 1/sec).
_RATE_LIMITER_LOCK = threading.Lock()
_RATE_LIMITER_STATE: dict[str, tuple[float, float]] = {}  # key -> (tokens, last_refill)


class _RateLimiter:
    """Token-bucket limiter for outbound API calls.

    Per-bucket defaults: 1 token/second refill, burst of 4. The bucket
    is identified by an arbitrary string (we use the API key, so the
    same key on the same provider shares the bucket regardless of how
    many summarizer instances exist).
    """

    def __init__(self, refill_per_sec: float = 1.0, burst: float = 4.0) -> None:
        self.refill_per_sec = refill_per_sec
        self.burst = burst

    def take(self, key: str, cost: float = 1.0) -> None:
        while True:
            with _RATE_LIMITER_LOCK:
                tokens, last = _RATE_LIMITER_STATE.get(key, (self.burst, time.monotonic()))
                now = time.monotonic()
                tokens = min(self.burst, tokens + (now - last) * self.refill_per_sec)
                if tokens >= cost:
                    _RATE_LIMITER_STATE[key] = (tokens - cost, now)
                    return
                # Not enough tokens — sleep until we have one, then retry.
                deficit = cost - tokens
                sleep_for = deficit / self.refill_per_sec
                _RATE_LIMITER_STATE[key] = (tokens, now)
            time.sleep(min(0.5, sleep_for))


class _LLMBaseSummarizer(BaseSummarizer):
    def __init__(
        self,
        api_key: str | None = None,
        model: str = "",
        fallback: BaseSummarizer | None = None,
        rate_limiter: _RateLimiter | None = None,
    ):
        self.api_key = api_key or ""
        self.model = model
        self.fallback = fallback or HeuristicSummarizer()
        self._request_lock = threading.Lock()
        self._rate_limiter = rate_limiter or _RateLimiter()
        self._rate_key = self.api_key or "default"

    def _throttle(self) -> None:
        self._rate_limiter.take(self._rate_key)

    def _execute_request(self, req: request.Request) -> dict[str, Any]:
        self._throttle()
        try:
            with request.urlopen(req, timeout=60) as response:
                data = json.loads(response.read().decode("utf-8"))
        except error.HTTPError as exc:
            if exc.code == 429:
                # Honor Retry-After if the provider sent one; otherwise wait 60s.
                retry_after = exc.headers.get("Retry-After") if exc.headers else None
                try:
                    wait = float(retry_after) if retry_after else 60.0
                except (TypeError, ValueError):
                    wait = 60.0
                logging.warning("Rate limited (429); waiting %.1fs", wait)
                time.sleep(wait)
                self._throttle()
                with request.urlopen(req, timeout=60) as response:
                    data = json.loads(response.read().decode("utf-8"))
            else:
                raise
        except error.URLError:
            raise
        return data

    def _parse_metadata(self, content: str, filename: str, text_snippet: str) -> FileMetadata:
        try:
            parsed = json.loads(content)
            tags = parsed.get("tags", [])
            if not isinstance(tags, list):
                tags = []
            category = str(parsed.get("category") or DEFAULT_CATEGORY)
            allowed_categories = {
                "Finance",
                "Research",
                "Design",
                "Code",
                "Media",
                "Personal",
                "Legal",
                "Other",
                "Duplicates",
            }
            if category not in allowed_categories:
                category = DEFAULT_CATEGORY
            clean_name = str(parsed.get("clean_name") or humanize_filename(filename)).strip() or humanize_filename(filename)
            fb = self.fallback or HeuristicSummarizer()
            return FileMetadata(
                summary=str(parsed.get("summary") or fb.get_file_metadata(filename, text_snippet).summary),
                tags=normalize_tags([str(tag) for tag in tags]),
                key_contents=str(parsed.get("key_contents") or ""),
                category=category,
                clean_name=clean_name,
            )
        except Exception:
            fb = self.fallback or HeuristicSummarizer()
            return fb.get_file_metadata(filename, text_snippet)

    def _chat_completion(self, system_prompt: str, user_prompt: str, model: str) -> str:
        raise NotImplementedError

    def _request_metadata(self, filename: str, text_snippet: str, system_prompt: str, user_prompt: str) -> FileMetadata:
        content = self._chat_completion(system_prompt, user_prompt, self.model)
        metadata = self._parse_metadata(content, filename, text_snippet)
        if metadata.summary and metadata.clean_name:
            return metadata
        retry_prompt = (
            user_prompt
            + "\n\nYour previous response was invalid. Return ONLY a JSON object with the required keys and no extra text."
        )
        content = self._chat_completion(system_prompt, retry_prompt, self.model)
        return self._parse_metadata(content, filename, text_snippet)

    def get_file_metadata(self, filename: str, text_snippet: str) -> FileMetadata:
        system_prompt = (
            "You are GOLEM, a file indexing assistant. "
            "Return only valid JSON with keys summary, tags, key_contents, category, clean_name."
        )
        user_prompt = (
            "Given a filename and a snippet of file content, infer the best metadata.\n"
            "Return pure JSON only.\n\n"
            f"File: {filename}\n"
            f"Content snippet: {text_excerpt(text_snippet, 300)}"
        )
        try:
            return self._request_metadata(filename, text_snippet, system_prompt, user_prompt)
        except Exception:
            fb = self.fallback or HeuristicSummarizer()
            return fb.get_file_metadata(filename, text_snippet)

    def search_rerank(self, query: str, candidates: list[dict[str, Any]]) -> str:
        if not self.api_key or not candidates:
            fb = self.fallback or HeuristicSummarizer()
            return fb.search_rerank(query, candidates)
        system_prompt = (
            "You are a file finder. Given a user description and candidate files, return only the filepath of the best match. "
            "If no file matches well, return exactly NOT_FOUND."
        )
        user_prompt = (
            f"User description: {query}\n\n"
            f"Candidate files: {json.dumps(candidates, ensure_ascii=False)}"
        )
        try:
            content = self._chat_completion(system_prompt, user_prompt, self.model).strip()
            if content == "NOT_FOUND":
                return content
            return content.splitlines()[0].strip()
        except Exception:
            fb = self.fallback or HeuristicSummarizer()
            return fb.search_rerank(query, candidates)


class OpenAICompatibleSummarizer(_LLMBaseSummarizer):
    def __init__(self, api_key: str | None = None, model: str = "", base_url: str = "", provider_key: str = "openai", fallback: BaseSummarizer | None = None):
        super().__init__(api_key=api_key, model=model, fallback=fallback)
        self.base_url = base_url.rstrip("/")
        self.provider_key = provider_key

    def _chat_completion(self, system_prompt: str, user_prompt: str, model: str) -> str:
        if not self.api_key:
            raise RuntimeError("API key missing")
        if not self.base_url:
            raise RuntimeError("Provider base URL missing")
        payload = json.dumps(
            {
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": 0.1,
            },
            ensure_ascii=False,
        ).encode("utf-8")
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        if self.provider_key == "openrouter":
            headers["HTTP-Referer"] = "https://github.com/ATLAS-DEV78423/Golem"
            headers["X-OpenRouter-Title"] = "GOLEM"
        req = request.Request(
            f"{self.base_url}/chat/completions",
            data=payload,
            headers=headers,
            method="POST",
        )
        with self._request_lock:
            data = self._execute_request(req)
        choices = data.get("choices", [])
        if not choices:
            raise RuntimeError("Provider response missing choices")
        message = choices[0].get("message", {}) if isinstance(choices[0], dict) else {}
        content = message.get("content", "") if isinstance(message, dict) else ""
        if not isinstance(content, str):
            raise RuntimeError("Provider response missing message content")
        return content


class AnthropicSummarizer(_LLMBaseSummarizer):
    def _chat_completion(self, system_prompt: str, user_prompt: str, model: str) -> str:
        if not self.api_key:
            raise RuntimeError("API key missing")
        payload = json.dumps(
            {
                "model": model,
                "max_tokens": 1024,
                "system": system_prompt,
                "messages": [{"role": "user", "content": user_prompt}],
                "temperature": 0.1,
            },
            ensure_ascii=False,
        ).encode("utf-8")
        req = request.Request(
            "https://api.anthropic.com/v1/messages",
            data=payload,
            headers={
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with self._request_lock:
            data = self._execute_request(req)
        parts = data.get("content", [])
        texts: list[str] = []
        for part in parts:
            if isinstance(part, dict) and part.get("type") == "text" and isinstance(part.get("text"), str):
                texts.append(part["text"])
        return "\n".join(texts).strip()


class GeminiSummarizer(_LLMBaseSummarizer):
    def _chat_completion(self, system_prompt: str, user_prompt: str, model: str) -> str:
        if not self.api_key:
            raise RuntimeError("API key missing")
        prompt = f"{system_prompt}\n\n{user_prompt}"
        payload = json.dumps(
            {
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": 0.1},
            },
            ensure_ascii=False,
        ).encode("utf-8")
        model_path = quote(model, safe="")
        req = request.Request(
            f"https://generativelanguage.googleapis.com/v1beta/models/{model_path}:generateContent",
            data=payload,
            headers={
                "x-goog-api-key": self.api_key,
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with self._request_lock:
            data = self._execute_request(req)
        candidates = data.get("candidates", [])
        texts: list[str] = []
        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            content = candidate.get("content", {})
            if not isinstance(content, dict):
                continue
            for part in content.get("parts", []):
                if isinstance(part, dict) and isinstance(part.get("text"), str):
                    texts.append(part["text"])
        return "\n".join(texts).strip()


class GroqSummarizer(OpenAICompatibleSummarizer):
    def __init__(self, api_key: str | None = None, model: str = "llama-3.1-8b-instant", fallback: BaseSummarizer | None = None):
        super().__init__(
            api_key=api_key or os.getenv("GROQ_API_KEY", ""),
            model=model,
            base_url="https://api.groq.com/openai/v1",
            provider_key="groq",
            fallback=fallback,
        )


def build_summarizer(provider: str, api_key: str | None, model: str = "", base_url: str = "") -> BaseSummarizer:
    provider_key = (provider or "heuristic").strip().lower()
    spec = PROVIDER_SPEC_MAP.get(provider_key)
    # If the user did not paste a key, fall back to the provider's
    # conventional environment variable. This is opt-in: a user who has
    # not configured a key and has not set the env var gets the heuristic
    # summarizer, which is always safe.
    effective_key = (api_key or "").strip()
    if not effective_key:
        env_var = PROVIDER_ENV_KEYS.get(provider_key)
        if env_var:
            effective_key = os.getenv(env_var, "").strip()
    if not effective_key or provider_key in {"", "heuristic", "none", "off"} or spec is None:
        return HeuristicSummarizer()
    selected_model = model.strip() or spec.default_model
    if spec.kind == "anthropic":
        return AnthropicSummarizer(api_key=effective_key, model=selected_model)
    if spec.kind == "gemini":
        return GeminiSummarizer(api_key=effective_key, model=selected_model)
    selected_base_url = base_url.strip() or spec.base_url
    if provider_key == "custom_openai" and not selected_base_url:
        return HeuristicSummarizer()
    return OpenAICompatibleSummarizer(api_key=effective_key, model=selected_model, base_url=selected_base_url, provider_key=provider_key)


def check_provider_connection(
    provider: str,
    api_key: str | None,
    model: str = "",
    base_url: str = "",
) -> tuple[bool, str]:
    """Send a trivial prompt to the provider and report whether it responded.

    Returns ``(ok, message)``. ``ok`` is True on any successful 200-class
    response with parseable JSON. The message is short — either the
    provider's own returned summary (truncated) or the error string.

    The test uses the same summarizer the app will use at scan time, so
    any auth / model / base-URL problem the user has configured is caught
    here, not on the first file. The fallback chain (heuristic on any
    failure) is bypassed by setting ``fallback=None`` — the user wants to
    know that THEIR key works, not that the heuristic does.
    """
    provider_key = (provider or "heuristic").strip().lower()
    if provider_key in {"", "heuristic", "none", "off"}:
        return (True, "Heuristic mode does not need a key.")
    if not api_key or not api_key.strip():
        return (False, "API key is empty. Paste your key or switch to Heuristic mode.")
    spec = PROVIDER_SPEC_MAP.get(provider_key)
    if spec is None:
        return (False, f"Unknown provider: {provider!r}")
    selected_model = (model or spec.default_model).strip()
    selected_base_url = (base_url or spec.base_url).strip()
    if spec.kind == "anthropic":
        summarizer: BaseSummarizer = AnthropicSummarizer(api_key=api_key, model=selected_model)
    elif spec.kind == "gemini":
        summarizer = GeminiSummarizer(api_key=api_key, model=selected_model)
    else:
        if not selected_base_url:
            return (False, "Base URL is required for this provider.")
        summarizer = OpenAICompatibleSummarizer(
            api_key=api_key, model=selected_model, base_url=selected_base_url, provider_key=provider_key
        )
    # Disable the heuristic fallback so a network error is surfaced,
    # not silently converted into a heuristic result. The base class
    # coerces ``fallback=None`` to ``HeuristicSummarizer()`` in __init__,
    # so we replace it with a stub that always raises.
    class _FailFallback(BaseSummarizer):
        def get_file_metadata(self, filename: str, text_snippet: str) -> FileMetadata:
            raise RuntimeError("provider call failed")
        def search_rerank(self, query: str, candidates: list[dict[str, Any]]) -> str:
            raise RuntimeError("provider call failed")
    summarizer.fallback = _FailFallback()
    try:
        metadata = summarizer.get_file_metadata(
            "golem-test.txt", "This is a short test of the API key and model."
        )
    except Exception as exc:
        return (False, f"{type(exc).__name__}: {exc}")
    preview = (metadata.summary or "").strip()
    if len(preview) > 120:
        preview = preview[:117] + "..."
    return (True, preview or f"OK ({provider_key})")
