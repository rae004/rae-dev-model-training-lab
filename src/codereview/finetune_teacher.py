"""Teacher-model client + prompt builders for ADR-029 generation.

The teacher writes specs, reviews, and chat text — never the code outputs
the student trains on. Talks to any OpenAI-compatible chat-completions
endpoint (provider + model tag pinned in configs/finetune_dataset.toml at
generation time; API key from the environment, never committed).

Stdlib `urllib` per the backend.py convention — one JSON POST shape isn't
worth a dependency.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class TeacherError(RuntimeError):
    """Raised when the teacher endpoint fails after retries."""


@dataclass(frozen=True)
class TeacherConfig:
    base_url: str  # e.g. "https://api.together.xyz/v1"
    model: str
    api_key: str
    temperature: float = 0.2
    timeout: float = 120.0
    retries: int = 3


class Teacher:
    def __init__(self, config: TeacherConfig) -> None:
        self._config = config

    def complete(self, *, system: str, user: str, max_tokens: int = 1024) -> str:
        cfg = self._config
        payload = json.dumps(
            {
                "model": cfg.model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "temperature": cfg.temperature,
                "max_tokens": max_tokens,
            }
        ).encode("utf-8")
        request = Request(
            f"{cfg.base_url.rstrip('/')}/chat/completions",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {cfg.api_key}",
            },
        )
        last_error: Exception | None = None
        for attempt in range(cfg.retries):
            try:
                with urlopen(request, timeout=cfg.timeout) as response:
                    body = json.loads(response.read().decode("utf-8"))
                return body["choices"][0]["message"]["content"]
            except (HTTPError, URLError, TimeoutError, KeyError, json.JSONDecodeError) as e:
                last_error = e
                time.sleep(2**attempt)
        raise TeacherError(f"teacher call failed after {cfg.retries} attempts: {last_error}")


# ---------- prompt builders -----------------------------------------------

SPEC_SYSTEM = """\
You write task instructions for a coding agent. Given a commit subject and
the unified diff of a single-file change, write the instruction a developer
would have given to request exactly that change.

Rules:
- Imperative voice, 1-4 sentences, plain text only.
- Name the concrete identifiers involved (functions, variables, types).
- Describe WHAT to change and WHY, never the literal replacement code.
- Do not mention commits, diffs, or version control - it is a task, not a
  description of a change that already happened.
"""


def build_spec_prompt(subject: str, diff: str) -> str:
    return (
        f"COMMIT SUBJECT: {subject}\n\nDIFF:\n```diff\n{diff}\n```\n\nWrite the task instruction."
    )


CHAT_QUESTION_SYSTEM = """\
You generate realistic developer questions. Given source material from a
repository (code, docs, or a design decision), write ONE question its owner
might ask an assistant about it. Concrete and answerable from the material
alone. Plain text, one sentence, no preamble.
"""


def build_chat_question_prompt(context: str) -> str:
    return f"SOURCE MATERIAL:\n{context}\n\nWrite the question."


CHAT_ANSWER_SYSTEM = """\
You answer questions about a repository for its owner. Style rules, strict:
- Concise, factual, focused on the goal of the question.
- Hard cap {max_words} words unless the question explicitly asks you to
  elaborate.
- No sidetracks, no adjacent concerns, no suggestions that were not asked
  for. Answer the question, stop.
- Prefer simplicity over cleverness in any code you reference.
"""


def build_chat_answer_system(max_words: int) -> str:
    return CHAT_ANSWER_SYSTEM.format(max_words=max_words)


def build_chat_answer_prompt(context: str, question: str) -> str:
    return f"SOURCE MATERIAL:\n{context}\n\nQUESTION: {question}"


@dataclass(frozen=True)
class Grounding:
    """ADR-031: owner-written material appended to the teacher's system
    prompt for chat answers and review references. The student never sees
    it — grounding shapes teacher outputs, not training records."""

    chat: str = ""
    review: str = ""


def with_grounding(system: str, grounding: str) -> str:
    if not grounding:
        return system
    return f"{system}\n{grounding}"
