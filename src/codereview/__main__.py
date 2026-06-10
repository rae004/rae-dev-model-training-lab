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
            "review (M7). Eval (M8) arrives in a later milestone."
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

    log.info("codereview %s — no subcommand given; see --help.", __version__)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
