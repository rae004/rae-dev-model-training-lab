import argparse
import logging
from pathlib import Path

from . import __version__
from .log import setup_logging


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="codereview",
        description=(
            "Code review assistant. Subcommands: train (M3), sample (M4). "
            "Review (M7) and eval (M8) arrive in later milestones."
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

    log.info("codereview %s — no subcommand given; see --help.", __version__)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
