"""Reverse mutations for the ADR-029 philosophy-targeted transform pairs.

Each named rule injects one anti-pattern into a real source file and pairs it
with a spec asking for the fix. The untouched original is the ground-truth
output — the model learns to produce the clean version a human actually
wrote, and the teacher never writes code (ADR-029).

Rules return None when a file doesn't contain the needed shape; the pipeline
tries the next candidate file. Python mutations are verified to still parse
(`ast.parse`) so the model never trains on syntactically broken input.

ADR-028 anchor coverage:
- noise_comments        -> "no comments unless the why is non-obvious"
- commented_out_code    -> "prefer simplicity; delete, don't keep dead code"
- defensive_validation  -> "no defensive validation of internal code"
- backcompat_alias      -> "no backwards-compat shims; just change the code"
- concrete_annotation   -> "public surfaces accept abstract types" (Python
  flavor of the interface-over-concrete anchor; the TS/CDK variant is
  covered by commit mining on the owner's repos and an ADR-030 eval case)
"""

from __future__ import annotations

import ast
import random
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Mutation:
    rule: str
    spec: str
    mutated: str
    original: str


def _parses(text: str) -> bool:
    try:
        ast.parse(text)
    except SyntaxError:
        return False
    return True


def _indent_of(line: str) -> str:
    return line[: len(line) - len(line.lstrip())]


# ---------- noise_comments ------------------------------------------------

_PY_STMT = re.compile(r"^(\s*)(\w[\w.]* *=[^=]|return )")
_TS_STMT = re.compile(r"^(\s*)(const |let |return )")

_NOISE_SPEC = (
    "Remove comments that merely restate what the code does. Keep comments "
    "that explain a non-obvious why (a hidden constraint, a workaround, a "
    "surprising behavior). Change nothing else."
)


def noise_comments(text: str, rng: random.Random, *, language: str) -> Mutation | None:
    pattern = _PY_STMT if language == "python" else _TS_STMT
    marker = "#" if language == "python" else "//"
    lines = text.splitlines(keepends=True)
    candidates = [i for i, line in enumerate(lines) if pattern.match(line)]
    if len(candidates) < 2:
        return None
    chosen = sorted(rng.sample(candidates, min(3, len(candidates))))
    out: list[str] = []
    for i, line in enumerate(lines):
        if i in chosen:
            stripped = line.strip().rstrip("\n")
            out.append(f"{_indent_of(line)}{marker} {_describe(stripped)}\n")
        out.append(line)
    mutated = "".join(out)
    if language == "python" and not _parses(mutated):
        return None
    return Mutation("noise_comments", _NOISE_SPEC, mutated, text)


def _describe(stmt: str) -> str:
    if stmt.startswith("return"):
        return "return the result"
    name = stmt.split("=")[0].split(":")[0].strip().removeprefix("const ").removeprefix("let ")
    return f"set {name}"


# ---------- commented_out_code --------------------------------------------

_DEAD_SPEC = (
    "Delete commented-out code. Version control already remembers it; dead "
    "code in comments only misleads. Leave real comments and all live code "
    "exactly as they are."
)


def commented_out_code(text: str, rng: random.Random, *, language: str) -> Mutation | None:
    marker = "#" if language == "python" else "//"
    lines = text.splitlines(keepends=True)
    pattern = _PY_STMT if language == "python" else _TS_STMT
    candidates = [i for i, line in enumerate(lines) if pattern.match(line)]
    if not candidates:
        return None
    at = rng.choice(candidates)
    block = lines[at : at + 2]
    dead = [f"{_indent_of(block[0])}{marker} {line.strip()}\n" for line in block if line.strip()]
    mutated = "".join(lines[:at] + dead + lines[at:])
    if language == "python" and not _parses(mutated):
        return None
    return Mutation("commented_out_code", _DEAD_SPEC, mutated, text)


# ---------- defensive_validation (python only) ----------------------------

_GUARD_SPEC = (
    "Remove redundant defensive validation from internal functions. Internal "
    "callers are trusted; only validate at system boundaries (user input, "
    "external APIs). Change nothing else."
)


def defensive_validation(text: str, rng: random.Random, *, language: str) -> Mutation | None:
    if language != "python":
        return None
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return None
    lines = text.splitlines(keepends=True)
    funcs = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.args.args and node.body
    ]
    if not funcs:
        return None
    func = rng.choice(funcs)
    arg = func.args.args[0].arg
    if arg in ("self", "cls"):
        if len(func.args.args) < 2:
            return None
        arg = func.args.args[1].arg
    # Insert after a docstring if present, so the docstring stays a docstring.
    body_start = func.body[0]
    if (
        isinstance(body_start, ast.Expr)
        and isinstance(body_start.value, ast.Constant)
        and isinstance(body_start.value.value, str)
        and len(func.body) > 1
    ):
        body_start = func.body[1]
    at = body_start.lineno - 1
    indent = _indent_of(lines[at])
    guard = f'{indent}if {arg} is None:\n{indent}    raise ValueError("{arg} must not be None")\n'
    mutated = "".join(lines[:at] + [guard] + lines[at:])
    if not _parses(mutated):
        return None
    return Mutation("defensive_validation", _GUARD_SPEC, mutated, text)


# ---------- backcompat_alias (python only) --------------------------------

_ALIAS_SPEC = (
    "Remove backwards-compatibility aliases. When a name changes, change it "
    "everywhere — do not keep the old name around as an alias. Change "
    "nothing else."
)


def backcompat_alias(text: str, rng: random.Random, *, language: str) -> Mutation | None:
    if language != "python":
        return None
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return None
    funcs = [node.name for node in tree.body if isinstance(node, ast.FunctionDef)]
    if not funcs:
        return None
    name = rng.choice(funcs)
    alias = f"\n\n# kept for backwards compatibility\nlegacy_{name} = {name}\n"
    mutated = text.rstrip("\n") + "\n" + alias
    if not _parses(mutated):
        return None
    return Mutation("backcompat_alias", _ALIAS_SPEC, mutated, text)


# ---------- concrete_annotation (python only) -----------------------------

# Subscripted or bare (`x: Sequence[int]` and `x: Sequence` both match).
_ABSTRACT_TO_CONCRETE = [
    ("Sequence", "list"),
    ("MutableMapping", "dict"),
    ("Mapping", "dict"),
    ("Iterable", "list"),
    ("Collection", "list"),
    ("Iterator", "list"),
]

_ANNOTATION_SPEC = (
    "Public functions should accept abstract types (e.g. Sequence, Mapping, "
    "Iterable) rather than concrete containers when they only iterate or "
    "look up. Widen the parameter annotations accordingly. Change nothing "
    "else."
)


def concrete_annotation(text: str, rng: random.Random, *, language: str) -> Mutation | None:
    if language != "python":
        return None
    swaps = [(a, c) for a, c in _ABSTRACT_TO_CONCRETE if re.search(rf": {a}\b", text)]
    if not swaps:
        return None
    abstract, concrete = rng.choice(swaps)
    mutated = re.sub(rf": {abstract}\b", f": {concrete}", text, count=1)
    if mutated == text or not _parses(mutated):
        return None
    return Mutation("concrete_annotation", _ANNOTATION_SPEC, mutated, text)


RULES = {
    "noise_comments": noise_comments,
    "commented_out_code": commented_out_code,
    "defensive_validation": defensive_validation,
    "backcompat_alias": backcompat_alias,
    "concrete_annotation": concrete_annotation,
}
