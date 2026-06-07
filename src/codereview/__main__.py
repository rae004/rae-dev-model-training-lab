import argparse
import logging
from pathlib import Path

from . import __version__
from .config import load_config
from .log import setup_logging


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="codereview",
        description=(
            "Code review assistant — learning-first scaffold. "
            "Subcommands (train, review, eval) arrive in later milestones."
        ),
    )
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument(
        "--config",
        type=Path,
        help="Path to a TOML config file (typically under configs/).",
    )
    parser.add_argument(
        "--log-level",
        default=None,
        help="DEBUG, INFO, WARNING, ERROR. Defaults to CODEREVIEW_LOG_LEVEL or INFO.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    setup_logging(args.log_level)
    log = logging.getLogger("codereview")

    if args.config is not None:
        config = load_config(args.config)
        log.info("loaded config from %s with top-level keys: %s", args.config, sorted(config))

    log.info("codereview %s — no command given; see --help.", __version__)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
