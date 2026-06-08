import argparse
import logging
from pathlib import Path

from . import __version__
from .log import setup_logging


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="codereview",
        description=(
            "Code review assistant. Subcommands: train (M3). Review (M7) and "
            "eval (M8) arrive in later milestones."
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

    log.info("codereview %s — no subcommand given; see --help.", __version__)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
