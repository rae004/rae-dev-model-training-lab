import argparse
import logging
from pathlib import Path

from . import __version__
from .log import setup_logging


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="codereview",
        description=(
            "Code review assistant. Subcommands: train (M3), sample (M4), "
            "review (M7), eval (M8), transform-eval + tool-smoke (M11)."
        ),
    )
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument(
        "--log-level",
        default=None,
        help="DEBUG, INFO, WARNING, ERROR. Defaults to CODEREVIEW_LOG_LEVEL or INFO.",
    )

    subparsers = parser.add_subparsers(dest="command", title="commands")

    train = subparsers.add_parser(
        "train",
        help="Train a GPT from a TOML config (M3).",
        description="Train a GPT from a TOML config under configs/.",
    )
    train.add_argument(
        "--config",
        type=Path,
        required=True,
        help="Path to a training config (e.g., configs/smoke.toml).",
    )
    train.add_argument(
        "--device",
        choices=["cpu", "cuda", "auto"],
        default=None,
        help="Override the config's device preference.",
    )
    train.add_argument(
        "--resume",
        type=Path,
        default=None,
        help="Path to a checkpoint to resume from (e.g., runs/smoke/ckpt.pt).",
    )

    sample = subparsers.add_parser(
        "sample",
        help="Generate text from a trained checkpoint (M4).",
        description="Sample text from a trained model.",
    )
    sample.add_argument("--checkpoint", type=Path, required=True, help="Path to a ckpt.pt.")
    sample.add_argument("--prompt", type=str, default="", help="Prompt to seed generation.")
    sample.add_argument(
        "--max-new-tokens",
        type=int,
        default=200,
        help="How many tokens to sample after the prompt.",
    )
    sample.add_argument(
        "--temperature",
        type=float,
        default=0.8,
        help="Sampling temperature (>0). Higher = more random.",
    )
    sample.add_argument(
        "--top-k",
        type=int,
        default=40,
        help="Restrict sampling to the top-k logits at each step.",
    )
    sample.add_argument(
        "--device",
        choices=["cpu", "cuda", "auto"],
        default="auto",
        help="Device preference for the checkpoint.",
    )
    sample.add_argument("--seed", type=int, default=None, help="Optional sampling seed.")

    review_p = subparsers.add_parser(
        "review",
        help="Review a diff via the configured backend (M7).",
        description=(
            "Read a diff from stdin, send it to the configured backend, "
            "and emit a Review on stdout. Exits non-zero if the verdict fails."
        ),
    )
    review_p.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Path to a review config (e.g., configs/review.toml). Defaults apply if omitted.",
    )
    review_p.add_argument(
        "--json",
        action="store_true",
        help="Emit the raw Review object as JSON instead of the text rendering.",
    )
    review_p.add_argument(
        "--threshold",
        choices=["error", "warning", "info"],
        default=None,
        help="Override config's verdict threshold.",
    )
    review_p.add_argument(
        "--backend-url",
        default=None,
        help="Override config's backend.base_url (e.g., http://workhorse:11434).",
    )
    review_p.add_argument(
        "--model",
        default=None,
        help="Override config's backend.model (e.g., qwen2.5-coder).",
    )

    eval_p = subparsers.add_parser(
        "eval",
        help="Score review() against a hand-authored eval set (M8).",
        description=(
            "Run every case in --eval-set through the configured backend, "
            "compare to reference findings, and print a precision-aware report."
        ),
    )
    eval_p.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Path to a review config (e.g., configs/review.toml). Defaults apply if omitted.",
    )
    eval_p.add_argument(
        "--eval-set",
        type=Path,
        default=Path("eval/eval_set.toml"),
        help="Path to the eval set TOML (default: eval/eval_set.toml).",
    )
    eval_p.add_argument(
        "--report",
        type=Path,
        default=None,
        help="If given, write the markdown report to this path (otherwise stdout).",
    )
    eval_p.add_argument(
        "--backend-url",
        default=None,
        help="Override config's backend.base_url.",
    )
    eval_p.add_argument(
        "--model",
        default=None,
        help="Override config's backend.model.",
    )

    teval = subparsers.add_parser(
        "transform-eval",
        help="Score single-file transforms against the hand-authored set (M11).",
        description=(
            "Run every case in --transform-set through the backend with the "
            "serving transform prompt and score the three ADR-030 booleans "
            "plus the runaway guard."
        ),
    )
    teval.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Path to a review config for the [backend] table. Defaults apply if omitted.",
    )
    teval.add_argument(
        "--transform-set",
        type=Path,
        default=Path("eval/transform_set.toml"),
        help="Path to the transform set TOML (default: eval/transform_set.toml).",
    )
    teval.add_argument(
        "--report",
        type=Path,
        default=None,
        help="If given, write the markdown report to this path (otherwise stdout).",
    )
    teval.add_argument("--backend-url", default=None, help="Override config's backend.base_url.")
    teval.add_argument("--model", default=None, help="Override config's backend.model.")
    teval.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Ollama sampling seed; with temperature 0 this makes runs deterministic.",
    )

    smoke = subparsers.add_parser(
        "tool-smoke",
        help="Measure the model's tool-calling rate (ADR-030 tripwire).",
        description=(
            "Send the canned prompts + tool schemas to Ollama /api/chat and "
            "report how often the model answers with a well-formed tool call."
        ),
    )
    smoke.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Path to a review config for the [backend] table. Defaults apply if omitted.",
    )
    smoke.add_argument(
        "--smoke-set",
        type=Path,
        default=Path("eval/tool_smoke.toml"),
        help="Path to the smoke set TOML (default: eval/tool_smoke.toml).",
    )
    smoke.add_argument("--backend-url", default=None, help="Override config's backend.base_url.")
    smoke.add_argument("--model", default=None, help="Override config's backend.model.")
    smoke.add_argument("--seed", type=int, default=42, help="Ollama sampling seed.")

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    setup_logging(args.log_level)
    log = logging.getLogger("codereview")

    if args.command == "train":
        # Lazy import — `codereview --help` shouldn't load torch.
        from .train import train_from_config_path

        result = train_from_config_path(
            args.config,
            override_device=args.device,
            resume_from=args.resume,
        )
        log.info(
            "training done: param_count=%d initial_train_loss=%.4f final_train_loss=%.4f",
            result["param_count"],
            result["initial_eval"]["train"],
            result["final_eval"]["train"],
        )
        return 0

    if args.command == "sample":
        from .sample import sample_from_checkpoint

        text = sample_from_checkpoint(
            args.checkpoint,
            args.prompt,
            max_new_tokens=args.max_new_tokens,
            temperature=args.temperature,
            top_k=args.top_k,
            device_pref=args.device,
            seed=args.seed,
        )
        print(text)
        return 0

    if args.command == "review":
        import json as _json
        import sys

        from .config import load_config
        from .review import (
            ReviewConfig,
            Severity,
            render_text,
            review,
            review_to_jsonable,
        )

        cfg_dict = load_config(args.config) if args.config is not None else {}
        cfg = ReviewConfig.from_dict(cfg_dict)
        if args.threshold:
            cfg.threshold = Severity(args.threshold)
        if args.backend_url:
            cfg.backend.base_url = args.backend_url
        if args.model:
            cfg.backend.model = args.model

        diff = sys.stdin.read()
        if not diff.strip():
            print("error: no diff on stdin (pipe `git diff` in)", file=sys.stderr)
            return 2

        try:
            result = review(diff, cfg)
        except Exception as e:
            print(f"error: review failed: {e}", file=sys.stderr)
            return 2

        if args.json:
            print(_json.dumps(review_to_jsonable(result), indent=2))
        else:
            print(render_text(result))

        assert result.verdict is not None
        return 0 if result.verdict.passed else 1

    if args.command == "eval":
        import sys

        from .config import load_config
        from .eval import load_eval_set, render_report, run_eval
        from .review import ReviewConfig

        cfg_dict = load_config(args.config) if args.config is not None else {}
        cfg = ReviewConfig.from_dict(cfg_dict)
        if args.backend_url:
            cfg.backend.base_url = args.backend_url
        if args.model:
            cfg.backend.model = args.model

        cases = load_eval_set(args.eval_set)
        if not cases:
            print(f"error: no cases found in {args.eval_set}", file=sys.stderr)
            return 2

        log.info("running %d eval case(s) against %s", len(cases), cfg.backend.base_url)
        try:
            report = run_eval(cases, cfg)
        except Exception as e:
            print(f"error: eval failed: {e}", file=sys.stderr)
            return 2

        text = render_report(report)
        if args.report:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(text, encoding="utf-8")
            log.info("wrote report to %s", args.report)
        else:
            print(text)
        return 0

    if args.command == "transform-eval":
        import sys

        from .backend import OllamaBackend
        from .config import load_config
        from .review import ReviewConfig
        from .transform_eval import load_transform_set, render_report, run_transform_eval

        cfg_dict = load_config(args.config) if args.config is not None else {}
        cfg = ReviewConfig.from_dict(cfg_dict)
        if args.backend_url:
            cfg.backend.base_url = args.backend_url
        if args.model:
            cfg.backend.model = args.model

        try:
            cases = load_transform_set(args.transform_set)
        except (OSError, ValueError, KeyError) as e:
            print(f"error: bad transform set {args.transform_set}: {e}", file=sys.stderr)
            return 2
        backend = OllamaBackend(
            base_url=cfg.backend.base_url,
            model=cfg.backend.model,
            timeout=cfg.backend.timeout,
            temperature=0.0,  # determinism; the harness never wants sampling variety
            num_thread=cfg.backend.num_thread,
            seed=args.seed,
        )
        log.info("running %d transform case(s) against %s", len(cases), cfg.backend.base_url)
        try:
            results = run_transform_eval(cases, backend)
        except Exception as e:
            print(f"error: transform eval failed: {e}", file=sys.stderr)
            return 2
        text = render_report(results, model=cfg.backend.model)
        if args.report:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(text, encoding="utf-8")
            log.info("wrote report to %s", args.report)
        else:
            print(text)
        return 0

    if args.command == "tool-smoke":
        import sys

        from .config import load_config
        from .review import ReviewConfig
        from .tool_smoke import load_tool_smoke, render_report, run_tool_smoke

        cfg_dict = load_config(args.config) if args.config is not None else {}
        cfg = ReviewConfig.from_dict(cfg_dict)
        if args.backend_url:
            cfg.backend.base_url = args.backend_url
        if args.model:
            cfg.backend.model = args.model

        tools, prompts, threshold = load_tool_smoke(args.smoke_set)
        log.info("running %d smoke prompt(s) against %s", len(prompts), cfg.backend.base_url)
        try:
            results = run_tool_smoke(
                tools,
                prompts,
                base_url=cfg.backend.base_url,
                model=cfg.backend.model,
                timeout=cfg.backend.timeout,
                seed=args.seed,
            )
        except Exception as e:
            print(f"error: tool smoke failed: {e}", file=sys.stderr)
            return 2
        print(render_report(results, model=cfg.backend.model, threshold=threshold))
        rate = sum(r.tool_called for r in results) / len(results)
        return 0 if threshold is None or rate >= threshold else 1

    log.info("codereview %s — no subcommand given; see --help.", __version__)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
