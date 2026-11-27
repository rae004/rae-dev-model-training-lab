"""End-to-end ADR-029 dataset assembly.

Order of operations (teacher writes prose, never code):

1. Mine single-file commits from every source repo (finetune_mine).
2. Teacher writes a task spec per mined commit -> transform pairs.
3. Mutation rules inject anti-patterns into sampled files -> transform pairs
   with pristine-original ground truth (finetune_mutate).
4. Decline pairs derived from commit-mined specs x non-matching files
   (finetune_decline).
5. Teacher reviews mined diffs -> review pairs (prioritized toward M9
   weakness keywords - a heuristic sighting, not semantic search).
6. Teacher generates chat Q&A from owner-repo material.
7. Gates + dedupe + composition report (finetune_compose).
"""

from __future__ import annotations

import difflib
import random
from dataclasses import dataclass
from typing import Any, Protocol

from codereview.finetune_compose import compose_report, dedupe, validate_record
from codereview.finetune_decline import (
    SpecSource,
    TargetFile,
    derive_declines,
    spec_identifiers,
)
from codereview.finetune_mine import MinedCommit, estimate_tokens
from codereview.finetune_mutate import RULES
from codereview.finetune_serialize import (
    chat_record,
    decline_record,
    review_record,
    transform_record,
)
from codereview.finetune_teacher import (
    CHAT_QUESTION_SYSTEM,
    SPEC_SYSTEM,
    Grounding,
    build_chat_answer_prompt,
    build_chat_answer_system,
    build_chat_question_prompt,
    build_spec_prompt,
    with_grounding,
)
from codereview.review import SYSTEM_PROMPT as REVIEW_SYSTEM_PROMPT

# M9 weakness-profile keywords - mined diffs matching these are preferred
# for the review slice (performance patterns, subtle bugs, security).
_M9_KEYWORDS = ("query", "select", "loop", "range", "async", "await", "retry", "secret", "sql")


class TeacherLike(Protocol):
    def complete(self, *, system: str, user: str, max_tokens: int = 1024) -> str: ...


@dataclass(frozen=True)
class SourceFiles:
    """Sampled files from one source repo, used for mutations and chat."""

    repo: str
    files: list[tuple[str, str]]  # (relative path, text)
    owner: bool = False  # ADR-029: only owner repos feed the chat slice


def unified_diff(rel: str, before: str, after: str) -> str:
    return "".join(
        difflib.unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            fromfile=f"a/{rel}",
            tofile=f"b/{rel}",
            n=3,
        )
    )


def build_dataset(
    mined: list[MinedCommit],
    sources: list[SourceFiles],
    teacher: TeacherLike,
    config: dict[str, Any],
    grounding: Grounding | None = None,
) -> tuple[list[dict[str, Any]], str]:
    """Assemble the dataset; returns (records, composition report)."""
    rng = random.Random(config["dataset"]["seed"])
    total = config["dataset"]["target_total"]
    props = config["proportions"]
    limits = config["limits"]
    counts = {shape: int(total * props[shape]) for shape in props}
    min_per_rule = config["mutations"]["min_pairs_per_rule"]
    # Overrides relax the report gate only — the sampling budget below stays
    # on the default minimum so adding an override never changes which pairs
    # a given seed generates.
    min_overrides = config["mutations"].get("min_overrides", {})

    records: list[dict[str, Any]] = []
    specs: list[SpecSource] = []
    grounding = grounding or Grounding()

    # -- mutation transforms (no teacher involved) --
    # ADR-031 dropped run3's //2 cap (mined pairs reserved half the slice):
    # philosophy rules now take what their minimums need and mined pairs
    # fill the remainder.
    mutation_budget = min(len(RULES) * min_per_rule, counts["transform"])
    records += _mutation_pairs(sources, rng, mutation_budget)

    # -- commit-mined transforms (teacher writes the spec only) --
    mined_budget = counts["transform"] - len(records)
    mined_pool = list(mined)
    rng.shuffle(mined_pool)
    for commit in mined_pool[:mined_budget]:
        diff = unified_diff(commit.path, commit.before, commit.after)
        spec = teacher.complete(
            system=SPEC_SYSTEM, user=build_spec_prompt(commit.subject, diff), max_tokens=300
        ).strip()
        changed = "".join(line[1:] for line in diff.splitlines(keepends=True) if line[:1] in "+-")
        specs.append(
            SpecSource(
                spec=spec,
                repo=commit.repo,
                identifiers=frozenset(spec_identifiers(spec, changed)),
            )
        )
        records.append(
            transform_record(
                spec,
                commit.path,
                commit.before,
                commit.after,
                {"repo": commit.repo, "sha": commit.sha},
            )
        )

    # -- declines (free: reuse specs against non-matching files) --
    targets = [
        TargetFile(repo=s.repo, path=rel, text=text) for s in sources for rel, text in s.files
    ]
    for d in derive_declines(specs, targets, rng, counts["decline"]):
        records.append(
            decline_record(
                d.spec,
                d.target_path,
                d.file_text,
                {"repo": d.target_repo, "spec_source": d.source_repo},
            )
        )

    # -- reviews (teacher output IS the training target; schema-gated later) --
    review_pool = sorted(
        mined_pool,
        key=lambda c: sum(k in (c.before + c.after).lower() for k in _M9_KEYWORDS),
        reverse=True,
    )
    for commit in review_pool[: counts["review"]]:
        diff = unified_diff(commit.path, commit.before, commit.after)
        review_json = teacher.complete(
            system=with_grounding(REVIEW_SYSTEM_PROMPT, grounding.review),
            user=f"```diff\n{diff}\n```",
            max_tokens=1024,
        ).strip()
        records.append(review_record(diff, review_json, {"repo": commit.repo, "sha": commit.sha}))

    # -- chat (teacher asks, then answers under the word cap) --
    # Owner repos only (ADR-029): the chat slice teaches conversation about
    # the owner's code in the owner's voice, not about the public corpus.
    owner_material = [(s.repo, rel, text) for s in sources if s.owner for rel, text in s.files]
    rng.shuffle(owner_material)
    answer_system = with_grounding(
        build_chat_answer_system(limits["max_chat_answer_words"]), grounding.chat
    )
    for repo, rel, text in owner_material[: counts["chat"]]:
        context = text[:6000]
        question = teacher.complete(
            system=CHAT_QUESTION_SYSTEM, user=build_chat_question_prompt(context), max_tokens=100
        ).strip()
        answer = teacher.complete(
            system=answer_system, user=build_chat_answer_prompt(context, question), max_tokens=400
        ).strip()
        records.append(chat_record(question, answer, {"repo": repo, "path": rel}))

    # -- gates, dedupe, report --
    gated = [
        r
        for r in records
        if validate_record(
            r,
            max_file_tokens=limits["max_file_tokens"],
            max_chat_answer_words=limits["max_chat_answer_words"],
        )
        is None
    ]
    final = dedupe(gated)
    report = compose_report(final, min_pairs_per_rule=min_per_rule, min_overrides=min_overrides)
    return final, report


def _mutation_pairs(
    sources: list[SourceFiles],
    rng: random.Random,
    budget: int,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    files = [(s.repo, rel, text) for s in sources for rel, text in s.files]
    rule_names = sorted(RULES)
    per_rule = {name: 0 for name in rule_names}
    # Each rule draws from its own shuffled pool so a (rule, file) combo is
    # tried at most once. Sampling with replacement here produced duplicate
    # pairs that the final dedupe collapsed, starving rules below minimum.
    pools: dict[str, list[tuple[str, str, str]]] = {}
    for name in rule_names:
        pool = list(files)
        rng.shuffle(pool)
        pools[name] = pool
    while len(records) < budget and any(pools.values()):
        # Round-robin toward the rule furthest below its minimum.
        rule_name = min((n for n in rule_names if pools[n]), key=lambda n: per_rule[n])
        repo, rel, text = pools[rule_name].pop()
        language = "python" if rel.endswith(".py") else "typescript"
        mutation = RULES[rule_name](text, rng, language=language)
        if mutation is None or estimate_tokens(mutation.mutated) > 3500:
            continue
        per_rule[rule_name] += 1
        records.append(
            transform_record(
                mutation.spec,
                rel,
                mutation.mutated,
                mutation.original,
                {"repo": repo, "rule": rule_name},
            )
        )
    return records
