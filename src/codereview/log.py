import logging
import os


def setup_logging(level: str | None = None) -> None:
    resolved = level or os.environ.get("CODEREVIEW_LOG_LEVEL", "INFO")
    logging.basicConfig(
        level=resolved.upper(),
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
