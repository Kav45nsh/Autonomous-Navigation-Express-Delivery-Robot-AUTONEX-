"""Console + rotating file logging. Call setup_logging() once, from main."""
import logging
import logging.handlers
import sys

from config import settings

_DONE = False


def setup_logging(level: str = None) -> None:
    global _DONE
    if _DONE:
        return
    fmt = logging.Formatter(
        "%(asctime)s %(levelname)-7s %(name)-28s %(message)s",
        datefmt="%H:%M:%S")

    root = logging.getLogger()
    root.setLevel(level or settings.LOG_LEVEL)

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(fmt)
    root.addHandler(console)

    fileh = logging.handlers.RotatingFileHandler(
        settings.LOG_DIR / "robot.log", maxBytes=2_000_000, backupCount=5)
    fileh.setFormatter(fmt)
    root.addHandler(fileh)

    _DONE = True
