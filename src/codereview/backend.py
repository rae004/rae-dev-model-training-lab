"""Pluggable backend protocol + an Ollama-HTTP implementation.

ADR-009 and ARCHITECTURE.md §2 put the model behind a swappable backend
chosen by config. For M7 we ship the Ollama-HTTP backend pointed at the
workhorse (`http://workhorse:11434`); the Protocol is here so a second
backend (e.g., a local in-process model) can be added without touching
review.py.

Uses stdlib `urllib` rather than adding `requests` / `httpx` — the call
shape is a single JSON POST, and keeping the main lockfile light is
worth the slightly more verbose code.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.error import URLError
from urllib.request import Request, urlopen


class BackendError(RuntimeError):
    """Raised when a backend call fails (network, non-200, malformed body)."""


class Backend(Protocol):
    def generate(self, *, system: str, user: str) -> str: ...


@dataclass
class OllamaBackend:
    base_url: str = "http://workhorse:11434"
    model: str = "qwen2.5-coder"
    timeout: float = 60.0
    temperature: float = 0.2
    # Threads for the llama.cpp inference loop. None → let Ollama auto-pick.
    # On the workhorse (i7-8700, 6c/12t) setting this to 6–8 measurably
    # improves single-stream throughput; scaling beyond is sub-linear due
    # to hyperthread / cache contention.
    num_thread: int | None = None

    def generate(self, *, system: str, user: str) -> str:
        url = f"{self.base_url.rstrip('/')}/api/generate"
        options: dict[str, Any] = {"temperature": self.temperature}
        if self.num_thread is not None:
            options["num_thread"] = self.num_thread
        body: dict[str, Any] = {
            "model": self.model,
            "system": system,
            "prompt": user,
            "stream": False,
            "options": options,
        }
        request = Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout) as resp:
                payload_bytes = resp.read()
        except URLError as e:
            raise BackendError(f"Ollama call to {url} failed: {e}") from e

        try:
            payload = json.loads(payload_bytes)
        except json.JSONDecodeError as e:
            raise BackendError(f"Ollama returned non-JSON ({len(payload_bytes)} bytes): {e}") from e

        if not isinstance(payload, dict) or "response" not in payload:
            raise BackendError(f"Ollama response missing 'response' field: {payload!r}")
        return str(payload["response"])
